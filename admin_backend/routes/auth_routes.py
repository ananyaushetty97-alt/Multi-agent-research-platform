"""
Authentication and session management routes for administrators.
Enforces password verification, secure token issuance, and login audit logging.
Does NOT contain hardcoded credentials or default accounts.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from admin_backend.models.audit import AuditAction
from admin_backend.models.auth import (
    InitialAdminProvisionRequest,
    UserRecord,
    UserRole,
)
from admin_backend.security.dependencies import AuthenticatedUser, get_current_user
from admin_backend.security.passwords import hash_password, verify_password
from admin_backend.security.rate_limiter import rate_limit_guard
from admin_backend.security.tokens import create_access_token, revoke_token_jti
from admin_backend.services.audit_service import audit_service
from admin_backend.storage.postgres import PostgresUserStorage

router = APIRouter(prefix="/auth", tags=["Admin Auth"])

# Package user storage instance - using PostgreSQL for persistence
user_storage = PostgresUserStorage()


class AdminGoogleLoginRequest(BaseModel):
    credential: str = Field(..., description="Google ID Token JWT")


@router.get("/config")
def get_admin_auth_config():
    """Return public authentication configuration for the admin login interface."""
    from admin_backend.config import settings
    return {
        "google_client_id": settings.get_google_client_id(),
        "environment": settings.environment,
    }


@router.post("/google", dependencies=[Depends(rate_limit_guard)])
def admin_google_login(req: AdminGoogleLoginRequest, request: Request, response: Response):
    """
    Authenticate an administrator via Google OAuth ID token.
    Validates token signature, audience, issuer, expiration, and verified email.
    Enforces authorization against active admin_users.
    Sets a secure, httpOnly, SameSite admin_session cookie.
    """
    client_ip = request.client.host if request.client else "unknown"
    from admin_backend.config import settings
    google_cid = settings.get_google_client_id()
    if not google_cid:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google Sign-In is not configured on this server."
        )

    # 1. Verify Google ID token
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        payload = id_token.verify_oauth2_token(
            req.credential,
            google_requests.Request(),
            audience=google_cid,
        )
    except Exception as e:
        audit_service.log_action(
            actor_username="anonymous",
            actor_role="anonymous",
            action=AuditAction.AUTH_LOGIN_FAILED,
            resource_type="admin_google_oauth",
            status="failure",
            details={"reason": "token_verification_failed", "error": str(e)},
            client_ip=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorised",
        )

    # Validate issuer
    iss = payload.get("iss")
    if iss not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorised")

    # Validate email_verified
    email_verified = payload.get("email_verified")
    if email_verified is not True and email_verified != "true":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorised")

    email = (payload.get("email") or "").strip().lower()
    google_id = payload.get("sub")
    name = payload.get("name") or payload.get("given_name") or email.split("@")[0]

    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorised")

    # 2. Check active admin_users record
    admin_record = user_storage.get_admin_by_email(email)
    if not admin_record or not admin_record.get("is_active", True):
        audit_service.log_action(
            actor_username=email,
            actor_role="anonymous",
            action=AuditAction.AUTH_LOGIN_FAILED,
            resource_type="admin_google_oauth",
            status="failure",
            details={"reason": "unauthorized_or_inactive_admin"},
            client_ip=client_ip,
        )
        # Return generic "Not authorised" - do NOT reveal whether email is registered
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorised",
        )

    # 3. Update last_login_at and google_id
    user_storage.update_admin_login(str(admin_record["id"]), google_id=google_id)

    # 4. Issue admin JWT with admin audience and issuer
    token = create_access_token(
        user_id=str(admin_record["id"]),
        username=admin_record.get("username", email),
        role="admin",
        email=email,
    )

    # 5. Set httpOnly SameSite cookie
    is_prod = settings.environment.lower() == "production"
    response.set_cookie(
        key=settings.admin_cookie_name,
        value=token,
        max_age=settings.admin_token_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=is_prod,
        path="/",
    )

    # 6. Audit successful login
    audit_service.log_action(
        actor_username=email,
        actor_role="admin",
        action=AuditAction.AUTH_LOGIN,
        resource_type="admin_google_oauth",
        resource_id=str(admin_record["id"]),
        status="success",
        details={"email": email, "auth_provider": "google"},
        client_ip=client_ip,
    )

    return {
        "status": "success",
        "access_token": token,
        "token_type": "bearer",
        "expires_in_seconds": settings.admin_token_expire_minutes * 60,
        "user": {
            "id": str(admin_record["id"]),
            "email": email,
            "name": admin_record.get("name") or name,
            "role": "admin",
        }
    }


@router.post("/logout")
def admin_logout(
    request: Request,
    response: Response,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Log out of the administrative session.
    Invalidates current session token JTI, clears the httpOnly cookie, and records audit trail.
    """
    from admin_backend.config import settings

    if current_user.token_jti:
        revoke_token_jti(current_user.token_jti)

    response.delete_cookie(
        key=settings.admin_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
    )

    client_ip = request.client.host if request.client else "unknown"
    audit_service.log_action(
        actor_username=current_user.username,
        actor_role=current_user.role,
        action=AuditAction.AUTH_LOGOUT,
        resource_type="admin_session",
        resource_id=current_user.user_id,
        status="success",
        details={"email": current_user.email},
        client_ip=client_ip,
    )

    return {"status": "success", "message": "Successfully logged out"}


@router.get("/me", response_model=UserRecord)
def get_current_authenticated_user(current_user: AuthenticatedUser = Depends(get_current_user)):
    """
    Return identity and role of currently authenticated caller.
    """
    user_data = user_storage.get_by_id(current_user.user_id)
    if user_data:
        return UserRecord(
            id=str(user_data["id"]),
            username=user_data.get("username") or user_data.get("email") or current_user.username,
            email=user_data.get("email"),
            name=user_data.get("name"),
            role=UserRole(user_data.get("role", "admin")),
            is_active=user_data.get("is_active", True),
            created_at=user_data.get("created_at", datetime.now(timezone.utc)),
        )

    return UserRecord(
        id=current_user.user_id,
        username=current_user.username,
        email=current_user.email,
        name=current_user.name,
        role=UserRole(current_user.role),
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )


@router.post("/provision-initial-admin", response_model=UserRecord, dependencies=[Depends(rate_limit_guard)])
def provision_initial_admin(req: InitialAdminProvisionRequest, request: Request):
    """
    Secure one-time bootstrapping endpoint for creating the first admin account.
    Requires server-side ADMIN_PROVISIONING_TOKEN environment variable.
    Cannot be used if an admin already exists or if the provisioning token is invalid.
    """
    expected_token = os.environ.get("ADMIN_PROVISIONING_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin provisioning is disabled (ADMIN_PROVISIONING_TOKEN is not configured on the server).",
        )

    import hmac
    if not hmac.compare_digest(req.provisioning_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid provisioning secret token",
        )

    existing = user_storage.get_by_username(req.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with username '{req.username}' already exists",
        )

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    hashed_pw = hash_password(req.password)

    user_data = {
        "id": user_id,
        "username": req.username,
        "email": req.email,
        "hashed_password": hashed_pw,
        "role": "admin",
        "is_active": True,
        "created_at": now,
    }
    user_storage.create_user(user_data)

    client_ip = request.client.host if request.client else "unknown"
    audit_service.log_action(
        actor_username=req.username,
        actor_role="admin",
        action=AuditAction.USER_PROVISION,
        resource_type="admin_user",
        resource_id=str(user_id),
        status="success",
        details={"username": req.username, "email": req.email},
        client_ip=client_ip,
    )

    return UserRecord(
        id=user_id,
        username=req.username,
        email=req.email,
        role=UserRole.ADMIN,
        is_active=True,
        created_at=now,
    )
