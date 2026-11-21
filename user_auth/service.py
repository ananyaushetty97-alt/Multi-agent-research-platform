import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
from fastapi import HTTPException, status

from admin_backend.security.passwords import hash_password, verify_password
from admin_backend.services.audit_service import audit_service
from admin_backend.models.audit import UserActivityAction
from user_auth.config import settings
from user_auth.models import (
    UserRegisterRequest,
    UserLoginRequest,
    GoogleLoginRequest,
    UserResponse,
)
from user_auth.security import (
    DUMMY_HASH,
    generate_session_token,
    hash_session_token,
    auth_security_manager,
)
from user_auth.storage import get_user_auth_storage, UserAuthStorageInterface

log = logging.getLogger("user_auth.service")


class UserAuthService:
    def __init__(self, storage: Optional[UserAuthStorageInterface] = None):
        self._storage_override = storage

    @property
    def storage(self) -> UserAuthStorageInterface:
        return self._storage_override or get_user_auth_storage()

    def _resolve_unique_username(self, base_email: str) -> str:
        """Generate collision-safe username for app_users.username (NOT NULL UNIQUE)."""
        base = base_email.split("@")[0][:80]
        candidate = base_email[:90]
        # Check collision
        existing = self.storage.get_user_by_email(candidate)
        if not existing:
            return candidate

        # Collision resolution
        for _ in range(5):
            suffix = secrets.token_hex(4)
            cand = f"{base[:80]}_{suffix}"
            if not self.storage.get_user_by_email(cand):
                return cand
        return f"user_{secrets.token_hex(8)}"

    def register(
        self,
        req: UserRegisterRequest,
        client_ip: str,
        user_agent: Optional[str] = None,
    ) -> Tuple[UserResponse, str]:
        """Register a new regular user with email + password."""
        email = req.email.strip().lower()

        # Duplicate email pre-check query (Condition 4)
        existing = self.storage.get_user_by_email(email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists. Try signing in.",
            )

        username = self._resolve_unique_username(email)
        user_id = str(uuid.uuid4())
        hashed_pw = hash_password(req.password)
        now = datetime.now(timezone.utc)

        user_data = {
            "id": user_id,
            "username": username,
            "email": email,
            "full_name": req.name,
            "hashed_password": hashed_pw,
            "role": "user",
            "is_active": True,
            "google_sub": None,
            "email_verified": False,
            "created_at": now,
        }
        created = self.storage.create_user(user_data)

        # Issue session
        raw_token = generate_session_token()
        token_hash = hash_session_token(raw_token)
        expires_at = now + timedelta(days=settings.session_cookie_max_age_days)

        self.storage.create_session({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "token_hash": token_hash,
            "created_at": now,
            "expires_at": expires_at,
            "revoked_at": None,
            "user_agent": user_agent,
            "ip": client_ip,
        })

        # Audit log registration
        try:
            audit_service.log_user_activity(
                session_id="auth",
                username=username,
                email=email,
                action=UserActivityAction.AUTH_LOGIN,
                topic="User Registration",
                status="success",
                client_ip=client_ip,
                user_agent=user_agent,
            )
        except Exception as e:
            log.warning(f"Could not log user activity: {type(e).__name__}: {e}")

        response = UserResponse(
            id=user_id,
            email=email,
            full_name=req.name,
            username=username,
            role="user",
            email_verified=False,
        )
        return response, raw_token

    def login(
        self,
        req: UserLoginRequest,
        client_ip: str,
        user_agent: Optional[str] = None,
    ) -> Tuple[UserResponse, str]:
        """
        Authenticate regular user with email + password.
        Strict verification order: PBKDF2 hash check first, then is_active (Condition 2).
        Hard-blocks demo user user@platform.ai when NEUTRALIZE_DEMO_USERS=true (Condition 1).
        """
        email = req.email.strip().lower()

        # Check account lockout
        is_locked, remaining = auth_security_manager.is_locked_out(email, client_ip)
        if is_locked:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account temporarily locked due to multiple failed attempts. Try again in {remaining} seconds.",
            )

        # Hard-block email user@platform.ai (Condition 1)
        if settings.neutralize_demo_users and email == "user@platform.ai":
            # Run dummy hash to prevent timing differentiation
            verify_password(req.password, DUMMY_HASH)
            auth_security_manager.record_failure(email, client_ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        user = self.storage.get_user_by_email(email)

        # Constant-time password check: always run PBKDF2 (Condition 2)
        password_ok = False
        if user and user.get("hashed_password"):
            password_ok = verify_password(req.password, user["hashed_password"])
        else:
            # Unknown email or Google-only account without password -> run dummy hash
            verify_password(req.password, DUMMY_HASH)
            password_ok = False

        if not user or not password_ok:
            auth_security_manager.record_failure(email, client_ip)
            try:
                audit_service.log_user_activity(
                    session_id="auth",
                    username=email,
                    email=email,
                    action=UserActivityAction.AUTH_LOGIN,
                    status="failure",
                    details={"reason": "invalid_credentials"},
                    client_ip=client_ip,
                    user_agent=user_agent,
                )
            except Exception as e:
                log.warning(f"Could not log user activity: {type(e).__name__}: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        # Revealed ONLY after password passes (Condition 2)
        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        # Success: reset lockout
        auth_security_manager.record_success(email, client_ip)

        now = datetime.now(timezone.utc)
        raw_token = generate_session_token()
        token_hash = hash_session_token(raw_token)
        expires_at = now + timedelta(days=settings.session_cookie_max_age_days)

        self.storage.create_session({
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "token_hash": token_hash,
            "created_at": now,
            "expires_at": expires_at,
            "revoked_at": None,
            "user_agent": user_agent,
            "ip": client_ip,
        })
        self.storage.update_user(user["id"], {"last_login": now})

        try:
            audit_service.log_user_activity(
                session_id="auth",
                username=user.get("username", email),
                email=email,
                action=UserActivityAction.AUTH_LOGIN,
                status="success",
                client_ip=client_ip,
                user_agent=user_agent,
            )
        except Exception as e:
            log.warning(f"Could not log user activity: {type(e).__name__}: {e}")

        response = UserResponse(
            id=str(user["id"]),
            email=user.get("email"),
            full_name=user.get("full_name"),
            username=user.get("username", email),
            role="user",
            email_verified=bool(user.get("email_verified", False)),
        )
        return response, raw_token

    def google_login(
        self,
        req: GoogleLoginRequest,
        client_ip: str,
        user_agent: Optional[str] = None,
    ) -> Tuple[UserResponse, str]:
        """
        Authenticate regular user with Google Identity Services ID-token.
        Enforces token signature, audience, and email_verified check.
        Never touches admin_users table (Hard Rule).
        """
        if not settings.google_client_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google OAuth is not configured on this server.",
            )

        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            payload = id_token.verify_oauth2_token(
                req.credential,
                google_requests.Request(),
                audience=settings.google_client_id,
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Google token verification failed: {e}",
            )

        # Reject invalid Google token issuer if present
        iss = payload.get("iss")
        if iss and iss not in ("accounts.google.com", "https://accounts.google.com"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google token issuer.",
            )

        # Reject unverified Google emails (supports boolean True or string "true")
        email_verified = payload.get("email_verified")
        if email_verified is not True and email_verified != "true":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google email is not verified.",
            )

        google_sub = payload.get("sub")
        email = (payload.get("email") or "").strip().lower()
        full_name = payload.get("name") or payload.get("given_name")

        if not google_sub or not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed Google identity claims.",
            )

        now = datetime.now(timezone.utc)
        user: Optional[Dict[str, Any]] = None

        # Case 1: Match by google_sub
        user = self.storage.get_user_by_google_sub(google_sub)

        # Case 2: Match by verified email
        if not user:
            existing_by_email = self.storage.get_user_by_email(email)
            if existing_by_email:
                user = existing_by_email
                # Reject Google linking if account has a different google_sub (Condition 8)
                existing_sub = user.get("google_sub")
                if existing_sub is not None and existing_sub != google_sub:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This email is already linked to a different Google account.",
                    )

                # Link account: set google_sub, set email_verified=True, CLEAR password_hash
                updates = {
                    "google_sub": google_sub,
                    "email_verified": True,
                    "hashed_password": None,  # Cleared to prevent pre-registration takeover
                }
                if full_name and not user.get("full_name"):
                    updates["full_name"] = full_name
                user = self.storage.update_user(user["id"], updates)

                # Revoke all existing sessions for this user (Condition 7)
                self.storage.revoke_all_user_sessions(user["id"])

        # Case 3: Create new regular user
        if not user:
            username = self._resolve_unique_username(email)
            user_id = str(uuid.uuid4())
            user_data = {
                "id": user_id,
                "username": username,
                "email": email,
                "full_name": full_name,
                "hashed_password": None,
                "role": "user",
                "is_active": True,
                "google_sub": google_sub,
                "email_verified": True,
                "created_at": now,
            }
            user = self.storage.create_user(user_data)

        # Reject inactive accounts (Condition 8)
        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        # Issue session
        raw_token = generate_session_token()
        token_hash = hash_session_token(raw_token)
        expires_at = now + timedelta(days=settings.session_cookie_max_age_days)

        self.storage.create_session({
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "token_hash": token_hash,
            "created_at": now,
            "expires_at": expires_at,
            "revoked_at": None,
            "user_agent": user_agent,
            "ip": client_ip,
        })
        self.storage.update_user(user["id"], {"last_login": now})

        try:
            audit_service.log_user_activity(
                session_id="auth",
                username=user.get("username", email),
                email=email,
                action=UserActivityAction.AUTH_LOGIN,
                topic="Google OAuth Login",
                status="success",
                client_ip=client_ip,
                user_agent=user_agent,
            )
        except Exception as e:
            log.warning(f"Could not log user activity: {type(e).__name__}: {e}")

        response = UserResponse(
            id=str(user["id"]),
            email=user.get("email"),
            full_name=user.get("full_name"),
            username=user.get("username", email),
            role="user",
            email_verified=True,
        )
        return response, raw_token

    def logout(self, raw_token: Optional[str], client_ip: str) -> None:
        """Revoke active session token."""
        if not raw_token:
            return
        token_hash = hash_session_token(raw_token)
        self.storage.revoke_session(token_hash)
        try:
            audit_service.log_user_activity(
                session_id="auth",
                username="user",
                action=UserActivityAction.AUTH_LOGOUT,
                topic="User Logout",
                status="success",
                client_ip=client_ip,
            )
        except Exception as e:
            log.warning(f"Could not log user activity: {type(e).__name__}: {e}")

    def get_user_from_session_token(self, raw_token: str) -> Optional[UserResponse]:
        """Look up user from raw session token. Checks expiry, revocation, and active status."""
        if not raw_token:
            return None
        token_hash = hash_session_token(raw_token)
        session = self.storage.get_session_by_token_hash(token_hash)
        if not session or session.get("revoked_at") is not None:
            return None

        # Expiry check
        now = datetime.now(timezone.utc)
        expires_at = session.get("expires_at")
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now > expires_at:
                return None

        user = self.storage.get_user_by_id(str(session["user_id"]))
        if not user or not user.get("is_active", True):
            return None

        return UserResponse(
            id=str(user["id"]),
            email=user.get("email"),
            full_name=user.get("full_name"),
            username=user.get("username", user.get("email", "")),
            role="user",
            email_verified=bool(user.get("email_verified", False)),
        )


auth_service = UserAuthService()
