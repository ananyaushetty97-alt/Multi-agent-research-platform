import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
from fastapi import HTTPException, status

from user_auth.config import settings
from user_auth.email_validator import validate_email_address, normalize_email
from user_auth.email_service import email_service
from user_auth.models import (
    UserRegisterRequest,
    UserLoginRequest,
    GoogleLoginRequest,
    VerifyOtpRequest,
    ResendOtpRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserResponse,
)
from user_auth.security import (
    DUMMY_HASH,
    hash_user_password,
    verify_user_password,
    generate_session_token,
    hash_session_token,
    generate_otp_code,
    hash_otp_code,
    generate_reset_token,
    hash_reset_token,
    auth_security_manager,
)
from user_auth.storage import get_user_auth_storage, UserAuthStorageInterface

# Alias for backwards compatibility / mock patching
verify_password = verify_user_password

log = logging.getLogger("user_auth.service")


class UserAuthService:
    def __init__(self, storage: Optional[UserAuthStorageInterface] = None):
        self._storage_override = storage

    @property
    def storage(self) -> UserAuthStorageInterface:
        return self._storage_override or get_user_auth_storage()

    def _resolve_unique_username(self, base_email: str) -> str:
        base = base_email.split("@")[0][:80]
        existing = self.storage.get_user_by_email(base_email)
        if not existing:
            return base
        for _ in range(5):
            suffix = secrets.token_hex(4)
            candidate = f"{base[:70]}_{suffix}"
            if not self.storage.get_user_by_email(candidate):
                return candidate
        return f"user_{secrets.token_hex(8)}"

    def register(
        self,
        req: UserRegisterRequest,
        client_ip: str,
        user_agent: Optional[str] = None,
    ) -> Tuple[UserResponse, str]:
        """
        Register a new regular user with email + password:
        - Layered email validation: syntax, disposable domain filter, DNS MX/A check.
        - Check duplicate email safely.
        - Hash password with bcrypt.
        - Generate and dispatch 6-digit OTP verification code.
        - Issue initial session.
        """
        # Multi-layer email validity check
        is_valid, email, err = validate_email_address(
            req.email, verify_dns=settings.verify_email_dns
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err,
            )

        # Duplicate email check
        existing = self.storage.get_user_by_email(email)
        if existing:
            # Check if this existing account is Google-linked or standard
            auth_prov = existing.get("auth_provider", "email")
            google_id = existing.get("google_id") or existing.get("google_sub")
            if google_id or auth_prov == "google":
                msg = "An account with this email already exists via Google. Please log in using 'Continue with Google', or use 'Forgot password' to set a password."
            else:
                msg = "An account with this email already exists. Please log in or use 'Forgot password' if you need to recover access."
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=msg,
            )

        user_id = str(uuid.uuid4())
        hashed_pw = hash_user_password(req.password)
        now = datetime.now(timezone.utc)
        username = self._resolve_unique_username(email)

        user_data = {
            "id": user_id,
            "name": req.name,
            "full_name": req.name,
            "username": username,
            "email": email,
            "password_hash": hashed_pw,
            "hashed_password": hashed_pw,
            "role": "user",
            "auth_provider": "email",
            "google_id": None,
            "google_sub": None,
            "email_verified": False,
            "status": "active",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        created = self.storage.create_user(user_data)

        # Generate OTP & link verification token
        otp = generate_otp_code()
        otp_hash = hash_otp_code(otp)
        link_token = generate_reset_token()
        link_token_hash = hash_reset_token(link_token)
        otp_expires = now + timedelta(minutes=settings.otp_expiry_minutes)

        self.storage.set_otp(
            user_id=user_id,
            email=email,
            otp_hash=otp_hash,
            token_hash=link_token_hash,
            expires_at=otp_expires,
        )

        # Dispatch verification email
        verify_link = f"{settings.app_base_url}/api/auth/verify?token={link_token}&email={email}"
        email_sent = email_service.send_verification_email(
            to_email=email,
            name=req.name,
            otp=otp,
            verify_link=verify_link,
        )
        if not email_sent and settings.email_configured:
            err_msg = email_service.last_error or "Delivery failed"
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not send the verification email: {err_msg}. Please check your address or try resending.",
            )

        # In unverified signup, NO session or cookie is issued until the OTP is verified.
        # Log activity
        self.storage.log_activity(
            user_id=user_id,
            event_type="signup",
            metadata={"email": email, "auth_provider": "email", "verified": False},
            ip_address=client_ip,
            user_agent=user_agent,
        )

        response = UserResponse(
            id=user_id,
            name=req.name,
            email=email,
            full_name=req.name,
            username=username,
            role="user",
            auth_provider="email",
            email_verified=False,
            status="active",
            created_at=now,
            updated_at=now,
        )
        return response, None

    def login(
        self,
        req: UserLoginRequest,
        client_ip: str,
        user_agent: Optional[str] = None,
    ) -> Tuple[UserResponse, str]:
        """
        Authenticate regular user with email + password.
        - Constant-time verification to prevent email enumeration.
        - Generic error message on unknown email or bad password.
        - Rejection of suspended accounts.
        - Session issuance and activity logging.
        """
        email = normalize_email(req.email)

        # Lockout check
        is_locked, remaining = auth_security_manager.is_locked_out(email, client_ip)
        if is_locked:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account temporarily locked due to multiple failed attempts. Try again in {remaining} seconds.",
            )

        # Hard-block neutralized demo user credentials
        if settings.neutralize_demo_users and email == "user@platform.ai":
            verify_password(req.password, DUMMY_HASH)
            auth_security_manager.record_failure(email, client_ip)
            self.storage.log_activity(
                user_id=None,
                event_type="login_failure",
                metadata={"email": email, "reason": "demo_user_neutralized"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        user = self.storage.get_user_by_email(email)

        # Constant-time password check
        pw_hash = user.get("password_hash") or user.get("hashed_password") if user else None
        if user and pw_hash:
            password_ok = verify_password(req.password, pw_hash)
        else:
            verify_password(req.password, DUMMY_HASH)
            password_ok = False

        if not user or not password_ok:
            auth_security_manager.record_failure(email, client_ip)
            self.storage.log_activity(
                user_id=str(user["id"]) if user else None,
                event_type="login_failure",
                metadata={"email": email, "reason": "invalid_credentials"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        # Check account status (suspended users cannot log in)
        user_status = user.get("status", "active")
        if not user.get("is_active", True):
            self.storage.log_activity(
                user_id=str(user["id"]),
                event_type="login_failure",
                metadata={"email": email, "reason": "account_deactivated"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )
        if user_status == "suspended":
            self.storage.log_activity(
                user_id=str(user["id"]),
                event_type="login_failure",
                metadata={"email": email, "reason": "account_suspended"},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been suspended. Please contact the administrator for assistance.",
            )

        # Account must be email-verified before session issuance
        if not user.get("email_verified", False):
            # Send fresh OTP respecting cooldown
            allowed, _ = auth_security_manager.check_otp_resend_cooldown(
                email, cooldown_seconds=settings.otp_resend_cooldown_seconds
            )
            email_sent = True
            delivery_err = None
            if allowed:
                otp = generate_otp_code()
                otp_hash = hash_otp_code(otp)
                link_token = generate_reset_token()
                link_token_hash = hash_reset_token(link_token)
                now_otp = datetime.now(timezone.utc)
                otp_expires = now_otp + timedelta(minutes=settings.otp_expiry_minutes)

                self.storage.set_otp(
                    user_id=str(user["id"]),
                    email=email,
                    otp_hash=otp_hash,
                    token_hash=link_token_hash,
                    expires_at=otp_expires,
                )
                verify_link = f"{settings.app_base_url}/api/auth/verify?token={link_token}&email={email}"
                email_sent = email_service.send_verification_email(
                    to_email=email,
                    name=user.get("name") or user.get("full_name") or "User",
                    otp=otp,
                    verify_link=verify_link,
                )
                if not email_sent and settings.email_configured:
                    delivery_err = email_service.last_error or "Delivery failed"

            if not email_sent and settings.email_configured:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Email verification required. Could not send the verification email: {delivery_err}. Please click Resend code.",
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email verification required. A new verification code has been sent to your email. Please verify your account before logging in.",
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
        self.storage.update_user(user["id"], {"last_login_at": now})

        # Log login success
        self.storage.log_activity(
            user_id=str(user["id"]),
            event_type="login_success",
            metadata={"email": email, "auth_provider": user.get("auth_provider", "email")},
            ip_address=client_ip,
            user_agent=user_agent,
        )

        response = UserResponse(
            id=str(user["id"]),
            name=user.get("name") or user.get("full_name") or "User",
            email=user.get("email"),
            full_name=user.get("full_name") or user.get("name"),
            username=user.get("username", email),
            role=user.get("role", "user"),
            auth_provider=user.get("auth_provider", "email"),
            email_verified=bool(user.get("email_verified", False)),
            status=user.get("status", "active"),
            google_id=user.get("google_id") or user.get("google_sub"),
            created_at=user.get("created_at"),
            updated_at=user.get("updated_at"),
            last_login_at=now,
        )
        return response, raw_token

    def verify_otp(
        self,
        req: VerifyOtpRequest,
        client_ip: str,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify email using 6-digit OTP code."""
        email = normalize_email(req.email)
        otp_rec = self.storage.get_otp_by_email(email)
        if not otp_rec:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No pending verification code found for this email. Please request a new one.",
            )

        # Check expiry
        now = datetime.now(timezone.utc)
        expires_at = otp_rec["expires_at"]
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now > expires_at:
                self.storage.delete_otp(email)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Verification code has expired. Please request a new code.",
                )

        # Check max attempts (5)
        attempts = otp_rec.get("attempts", 0)
        if attempts >= settings.otp_max_attempts:
            self.storage.delete_otp(email)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many invalid attempts. For security, this code was invalidated. Please request a new one.",
            )

        # Compare hashes
        expected_hash = otp_rec["otp_hash"]
        provided_hash = hash_otp_code(req.otp)
        if not secrets.compare_digest(expected_hash, provided_hash):
            new_attempts = self.storage.increment_otp_attempts(email)
            rem = max(0, settings.otp_max_attempts - new_attempts)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid verification code. {rem} attempts remaining.",
            )

        # Mark user verified and issue active session
        user = self.storage.get_user_by_email(email)
        if user:
            self.storage.update_user(user["id"], {"email_verified": True})
            self.storage.delete_otp(email)
            self.storage.log_activity(
                user_id=str(user["id"]),
                event_type="email_verified",
                metadata={"email": email, "method": "otp"},
                ip_address=client_ip,
                user_agent=user_agent,
            )

            # Issue session token so user is logged in automatically upon verification
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
            self.storage.update_user(user["id"], {"last_login_at": now})

            user_resp = UserResponse(
                id=str(user["id"]),
                name=user.get("name") or user.get("full_name") or "User",
                email=user.get("email"),
                full_name=user.get("full_name") or user.get("name") or "User",
                username=user.get("username", email),
                role=user.get("role", "user"),
                auth_provider=user.get("auth_provider", "email"),
                email_verified=True,
                status=user.get("status", "active"),
                google_id=user.get("google_id") or user.get("google_sub"),
                created_at=user.get("created_at"),
                updated_at=now,
            )
            return {
                "status": "ok",
                "message": "Email verified successfully!",
                "email_verified": True,
                "user": user_resp.model_dump(),
                "raw_token": raw_token,
            }

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User account not found.")

    def verify_token(
        self,
        token: str,
        email: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify email using signed single-use link token."""
        token_hash = hash_reset_token(token)
        otp_rec = self.storage.get_otp_by_token_hash(token_hash)
        if not otp_rec:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification link.",
            )

        now = datetime.now(timezone.utc)
        expires_at = otp_rec["expires_at"]
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now > expires_at:
                self.storage.delete_otp(otp_rec["email"])
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Verification link has expired. Please request a new code.",
                )

        target_email = otp_rec["email"]
        user = self.storage.get_user_by_email(target_email)
        if user:
            self.storage.update_user(user["id"], {"email_verified": True})
            self.storage.delete_otp(target_email)
            self.storage.log_activity(
                user_id=str(user["id"]),
                event_type="email_verified",
                metadata={"email": target_email, "method": "link"},
                ip_address=client_ip,
                user_agent=user_agent,
            )

            # Issue session token so user is logged in automatically upon link click
            raw_token = generate_session_token()
            token_hash_val = hash_session_token(raw_token)
            expires_at = now + timedelta(days=settings.session_cookie_max_age_days)
            self.storage.create_session({
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "token_hash": token_hash_val,
                "created_at": now,
                "expires_at": expires_at,
                "revoked_at": None,
                "user_agent": user_agent,
                "ip": client_ip,
            })
            self.storage.update_user(user["id"], {"last_login_at": now})

            user_resp = UserResponse(
                id=str(user["id"]),
                name=user.get("name") or user.get("full_name") or "User",
                email=user.get("email"),
                full_name=user.get("full_name") or user.get("name") or "User",
                username=user.get("username", target_email),
                role=user.get("role", "user"),
                auth_provider=user.get("auth_provider", "email"),
                email_verified=True,
                status=user.get("status", "active"),
                google_id=user.get("google_id") or user.get("google_sub"),
                created_at=user.get("created_at"),
                updated_at=now,
            )
            return {
                "status": "ok",
                "message": "Email verified successfully!",
                "email_verified": True,
                "user": user_resp.model_dump(),
                "raw_token": raw_token,
            }

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    def resend_otp(
        self,
        req: ResendOtpRequest,
        client_ip: str,
    ) -> Dict[str, Any]:
        """Resend OTP code respecting cooldown (60 seconds)."""
        email = normalize_email(req.email)
        allowed, wait_sec = auth_security_manager.check_otp_resend_cooldown(
            email, cooldown_seconds=settings.otp_resend_cooldown_seconds
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {wait_sec} seconds before requesting another verification code.",
            )

        user = self.storage.get_user_by_email(email)
        if not user:
            # Respond cleanly without enumeration
            return {"status": "ok", "message": "If this email is registered, a new code has been sent."}

        if user.get("email_verified", False):
            return {"status": "ok", "message": "This email is already verified. You can log in directly."}

        otp = generate_otp_code()
        otp_hash = hash_otp_code(otp)
        link_token = generate_reset_token()
        link_token_hash = hash_reset_token(link_token)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=settings.otp_expiry_minutes)

        self.storage.set_otp(
            user_id=str(user["id"]),
            email=email,
            otp_hash=otp_hash,
            token_hash=link_token_hash,
            expires_at=expires,
        )

        verify_link = f"{settings.app_base_url}/api/auth/verify?token={link_token}&email={email}"
        email_sent = email_service.send_verification_email(
            to_email=email,
            name=user.get("name") or user.get("full_name") or "User",
            otp=otp,
            verify_link=verify_link,
        )
        if not email_sent and settings.email_configured:
            err_msg = email_service.last_error or "Delivery failed"
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not send the verification email: {err_msg}. Please try again.",
            )
        return {"status": "ok", "message": "A new verification code has been sent to your email."}

    def request_password_reset(
        self,
        req: ForgotPasswordRequest,
        client_ip: str,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Initiate password reset request with random single-use token."""
        email = normalize_email(req.email)
        if not auth_security_manager.check_password_reset_limit(email):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many password reset requests. Please try again in an hour.",
            )

        user = self.storage.get_user_by_email(email)
        if user and user.get("status", "active") != "suspended":
            token = generate_reset_token()
            token_hash = hash_reset_token(token)
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(minutes=settings.reset_token_expiry_minutes)

            self.storage.create_password_reset(
                user_id=str(user["id"]),
                token_hash=token_hash,
                expires_at=expires_at,
            )

            reset_link = f"{settings.app_base_url}/user/index.html?view=reset-password&token={token}"
            email_service.send_password_reset_email(
                to_email=email,
                name=user.get("name") or user.get("full_name") or "User",
                reset_link=reset_link,
            )

            self.storage.log_activity(
                user_id=str(user["id"]),
                event_type="password_reset_requested",
                metadata={"email": email},
                ip_address=client_ip,
                user_agent=user_agent,
            )

        return {
            "status": "ok",
            "message": "If an account exists with this email, instructions to reset your password have been sent.",
        }

    def reset_password(
        self,
        req: ResetPasswordRequest,
        client_ip: str,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reset password with token.
        - Verifies token validity and single-use.
        - Hashes new password with bcrypt.
        - Invalidates all existing user sessions.
        """
        token_hash = hash_reset_token(req.token)
        reset_rec = self.storage.get_password_reset(token_hash)
        if not reset_rec or reset_rec.get("used_at") is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or already used password reset link. Please request a new one.",
            )

        now = datetime.now(timezone.utc)
        expires_at = reset_rec["expires_at"]
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now > expires_at:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This password reset link has expired. Please request a new one.",
                )

        user_id = str(reset_rec["user_id"])
        user = self.storage.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        new_hash = hash_user_password(req.password)
        updates = {
            "password_hash": new_hash,
            "hashed_password": new_hash,
            "email_verified": True,
        }
        if user.get("auth_provider") == "google":
            updates["auth_provider"] = "both"

        self.storage.update_user(user_id, updates)
        self.storage.mark_password_reset_used(token_hash)

        # Invalidate all active user sessions on password change
        self.storage.revoke_all_user_sessions(user_id)

        self.storage.log_activity(
            user_id=user_id,
            event_type="password_reset_completed",
            metadata={"email": user.get("email")},
            ip_address=client_ip,
            user_agent=user_agent,
        )

        return {"status": "ok", "message": "Password reset successfully. Please log in with your new password."}

    def google_login(
        self,
        req: GoogleLoginRequest,
        client_ip: str,
        user_agent: Optional[str] = None,
    ) -> Tuple[UserResponse, str]:
        """
        Authenticate regular user with Google Identity Services ID token.
        - Verified server-side.
        - Links to existing account if email matches.
        - Creates account if new.
        - Auto-verifies email.
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

        iss = payload.get("iss")
        if iss and iss not in ("accounts.google.com", "https://accounts.google.com"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google token issuer.",
            )

        email_verified = payload.get("email_verified")
        if email_verified is not True and email_verified != "true":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google email is not verified.",
            )

        google_sub = payload.get("sub")
        email = normalize_email(payload.get("email") or "")
        full_name = payload.get("name") or payload.get("given_name") or "Google User"

        if not google_sub or not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed Google identity claims.",
            )

        now = datetime.now(timezone.utc)
        user = self.storage.get_user_by_google_sub(google_sub)

        # If not found by google_sub, check by email to link account
        if not user:
            existing_by_email = self.storage.get_user_by_email(email)
            if existing_by_email:
                user = existing_by_email
                existing_sub = user.get("google_id") or user.get("google_sub")
                if existing_sub is not None and existing_sub != google_sub:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This email is already linked to a different Google account.",
                    )

                # Link Google ID and revoke all existing sessions to prevent takeover
                self.storage.revoke_all_user_sessions(user["id"])
                was_verified = bool(user.get("email_verified", False))
                auth_prov = "both" if (was_verified and (user.get("password_hash") or user.get("hashed_password"))) else "google"
                updates = {
                    "google_id": google_sub,
                    "google_sub": google_sub,
                    "email_verified": True,
                    "auth_provider": auth_prov,
                }
                if not was_verified:
                    # Clear password on unverified accounts to prevent pre-registration takeover
                    updates["password_hash"] = None
                    updates["hashed_password"] = None
                if full_name and not (user.get("name") or user.get("full_name")):
                    updates["name"] = full_name
                    updates["full_name"] = full_name
                user = self.storage.update_user(user["id"], updates)

        # If still not found, create new account
        if not user:
            username = self._resolve_unique_username(email)
            user_id = str(uuid.uuid4())
            user_data = {
                "id": user_id,
                "name": full_name,
                "full_name": full_name,
                "username": username,
                "email": email,
                "password_hash": None,
                "hashed_password": None,
                "role": "user",
                "auth_provider": "google",
                "google_id": google_sub,
                "google_sub": google_sub,
                "email_verified": True,
                "status": "active",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            user = self.storage.create_user(user_data)
            self.storage.log_activity(
                user_id=user_id,
                event_type="signup",
                metadata={"email": email, "auth_provider": "google"},
                ip_address=client_ip,
                user_agent=user_agent,
            )

        # Check account status
        if user.get("status") == "suspended" or not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been suspended. Please contact the administrator for assistance.",
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
        self.storage.update_user(user["id"], {"last_login_at": now})

        self.storage.log_activity(
            user_id=str(user["id"]),
            event_type="google_login",
            metadata={"email": email},
            ip_address=client_ip,
            user_agent=user_agent,
        )

        response = UserResponse(
            id=str(user["id"]),
            name=user.get("name") or user.get("full_name") or "User",
            email=user.get("email"),
            full_name=user.get("full_name") or user.get("name"),
            username=user.get("username", email),
            role=user.get("role", "user"),
            auth_provider=user.get("auth_provider", "google"),
            email_verified=True,
            status=user.get("status", "active"),
            google_id=user.get("google_id") or user.get("google_sub"),
            created_at=user.get("created_at"),
            updated_at=user.get("updated_at"),
            last_login_at=now,
        )
        return response, raw_token

    def logout(self, raw_token: Optional[str], client_ip: str) -> None:
        """Revoke active session token."""
        if not raw_token:
            return
        token_hash = hash_session_token(raw_token)
        session = self.storage.get_session_by_token_hash(token_hash)
        user_id = str(session["user_id"]) if session else None
        self.storage.revoke_session(token_hash)
        self.storage.log_activity(
            user_id=user_id,
            event_type="logout",
            metadata={},
            ip_address=client_ip,
        )

    def get_user_from_session_token(self, raw_token: str) -> Optional[UserResponse]:
        """Look up user from raw session token. Checks expiry, revocation, and active status."""
        if not raw_token:
            return None
        token_hash = hash_session_token(raw_token)
        session = self.storage.get_session_by_token_hash(token_hash)
        if not session or session.get("revoked_at") is not None:
            return None

        now = datetime.now(timezone.utc)
        expires_at = session.get("expires_at")
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now > expires_at:
                return None

        user = self.storage.get_user_by_id(str(session["user_id"]))
        if not user or user.get("status") == "suspended" or not user.get("is_active", True):
            return None

        return UserResponse(
            id=str(user["id"]),
            name=user.get("name") or user.get("full_name") or "User",
            email=user.get("email"),
            full_name=user.get("full_name") or user.get("name"),
            username=user.get("username", user.get("email", "")),
            role=user.get("role", "user"),
            auth_provider=user.get("auth_provider", "email"),
            email_verified=bool(user.get("email_verified", False)),
            status=user.get("status", "active"),
            google_id=user.get("google_id") or user.get("google_sub"),
            created_at=user.get("created_at"),
            updated_at=user.get("updated_at"),
            last_login_at=user.get("last_login_at"),
        )


auth_service = UserAuthService()
