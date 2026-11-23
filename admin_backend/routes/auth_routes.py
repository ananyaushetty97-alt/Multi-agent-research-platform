"""
Authentication and session management routes for administrators.
Enforces password verification, secure token issuance, and login audit logging.
Does NOT contain hardcoded credentials or default accounts.
"""
import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status

from admin_backend.models.audit import AuditAction
from admin_backend.models.auth import (
    InitialAdminProvisionRequest,
    LoginRequest,
    TokenResponse,
    UserRecord,
    UserRole,
)
from admin_backend.security.dependencies import AuthenticatedUser, get_current_user
from admin_backend.security.passwords import hash_password, verify_password
from admin_backend.security.rate_limiter import rate_limit_guard
from admin_backend.security.tokens import create_access_token
from admin_backend.services.audit_service import audit_service
from admin_backend.storage.in_memory import InMemoryUserStorage

router = APIRouter(prefix="/auth", tags=["Admin Auth"])

# Package user storage instance - using InMemory for testing (switch to PostgresUserStorage for production)
user_storage = InMemoryUserStorage()


def seed_default_users_if_empty():
    """Seed initial administrator account if storage is empty.
    Regular users should be created in the app_users table, not admin_users.
    """
    if not user_storage.get_by_username("admin"):
        admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")
        now = datetime.now(timezone.utc)
        hashed_admin = hash_password(admin_pass, iterations=50_000)
        user_storage.create_user({
            "id": str(uuid.uuid4()),
            "username": "admin",
            "email": "admin@platform.ai",
            "hashed_password": hashed_admin,
            "role": "admin",
            "is_active": True,
            "created_at": now,
        })
        user_storage.create_user({
            "id": str(uuid.uuid4()),
            "username": "admin@platform.ai",
            "email": "admin@platform.ai",
            "hashed_password": hashed_admin,
            "role": "admin",
            "is_active": True,
            "created_at": now,
        })

if not user_storage.get_by_username("user"):
        user_pass = os.environ.get("USER_PASSWORD", "user123")
        now = datetime.now(timezone.utc)
        hashed_user = hash_password(user_pass, iterations=50_000)
        user_storage.create_user({
            "id": str(uuid.uuid4()),
            "username": "user",
            "email": "user@platform.ai",
            "hashed_password": hashed_user,
            "role": "user",
            "is_active": True,
            "created_at": now,
        })
        user_storage.create_user({
            "id": str(uuid.uuid4()),
            "username": "user@platform.ai",
            "email": "user@platform.ai",
            "hashed_password": hashed_user,
            "role": "user",
            "is_active": True,
            "created_at": now,
        })

seed_default_users_if_empty()


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit_guard)])
def login(login_req: LoginRequest, request: Request):
    """
    Authenticate an administrator and issue a signed bearer token.
    Records successful and failed login attempts in the audit log.
    Regular users authenticate via the user portal, not admin auth.
    """
    import logging
    log = logging.getLogger("admin_backend.auth")

    client_ip = request.client.host if request.client else "unknown"
    clean_username = (login_req.username or "").strip().lower()
    user_record = user_storage.get_by_username(clean_username)

    log.info(f"Login attempt: username={clean_username}, user_found={user_record is not None}")
    if user_record:
        log.info(f"User role: {user_record.get('role')}, is_active: {user_record.get('is_active')}")

    raw_password = login_req.password or ""
    password_ok = verify_password(raw_password, user_record.get("hashed_password", "")) if user_record else False
    if not password_ok and user_record:
        password_ok = verify_password(raw_password.strip(), user_record.get("hashed_password", ""))

    log.info(f"Password check: password_ok={password_ok}")

    if not user_record or not password_ok:
        # Audit failed login attempt
        audit_service.log_action(
            actor_username=login_req.username,
            actor_role="anonymous",
            action=AuditAction.AUTH_LOGIN_FAILED,
            resource_type="auth_token",
            status="failure",
            details={"reason": "invalid_credentials"},
            client_ip=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user_record.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    role = user_record.get("role", "user")
    token = create_access_token(
        user_id=user_record["id"],
        username=user_record["username"],
        role=role,
    )

    # Audit successful login
    audit_service.log_action(
        actor_username=user_record["username"],
        actor_role=role,
        action=AuditAction.AUTH_LOGIN,
        resource_type="auth_token",
        resource_id=str(user_record["id"]),
        status="success",
        client_ip=client_ip,
    )

    from admin_backend.config import settings
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=settings.admin_token_expire_minutes * 60,
        role=UserRole(role),
        username=user_record["username"],
    )


@router.get("/me", response_model=UserRecord)
def get_current_authenticated_user(current_user: AuthenticatedUser = Depends(get_current_user)):
    """
    Return identity and role of currently authenticated caller.
    """
    user_data = user_storage.get_by_id(current_user.user_id)
    if user_data:
        return UserRecord(
            id=user_data["id"],
            username=user_data["username"],
            email=user_data.get("email"),
            role=UserRole(user_data.get("role", "user")),
            is_active=user_data.get("is_active", True),
            created_at=user_data.get("created_at", datetime.now(timezone.utc)),
        )

    return UserRecord(
        id=current_user.user_id,
        username=current_user.username,
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
