"""
FastAPI dependencies for authentication, role-based authorization,
rate limiting, and destructive action safeguards.
"""
from typing import Optional
from fastapi import Depends, Header, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from admin_backend.security.tokens import decode_access_token
from admin_backend.security.rate_limiter import rate_limit_guard

security_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    def __init__(
        self,
        user_id: str,
        username: str,
        role: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        token_jti: Optional[str] = None,
    ):
        self.user_id = str(user_id)
        self.username = username
        self.role = role
        self.email = email or username
        self.name = name or username
        self.token_jti = token_jti

    def is_admin(self) -> bool:
        return self.role == "admin"


# Storage instance for admin authorization verification
_user_storage = None

def _get_user_storage():
    global _user_storage
    if _user_storage is not None:
        return _user_storage
    try:
        from admin_backend.routes import auth_routes
        if getattr(auth_routes, "user_storage", None) is not None:
            return auth_routes.user_storage
    except Exception:
        pass
    from admin_backend.storage.postgres import PostgresUserStorage
    return PostgresUserStorage()


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> AuthenticatedUser:
    """
    Extract and validate admin authentication token from httpOnly cookie or Authorization header.
    Enforces token signature, expiration, issuer, audience, and real-time database active status.
    Protects state-changing requests against CSRF.
    """
    from admin_backend.config import settings

    token = None
    auth_source = None

    # 1. Prefer httpOnly cookie
    cookie_token = request.cookies.get(settings.admin_cookie_name)
    if cookie_token and cookie_token.strip():
        token = cookie_token.strip()
        auth_source = "cookie"
    # 2. Fall back to Authorization Bearer header
    elif credentials and credentials.credentials:
        token = credentials.credentials.strip()
        auth_source = "bearer"

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Decode & validate JWT
    try:
        payload = decode_access_token(token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    username = payload.get("username")
    role = payload.get("role", "admin")
    email = payload.get("email")
    token_jti = payload.get("jti")

    if not user_id or not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. Enforce CSRF protection on state-changing requests when authenticated via cookie
    if auth_source == "cookie" and request.method.upper() in ("POST", "PUT", "DELETE", "PATCH"):
        csrf_header = (
            request.headers.get("X-Requested-With")
            or request.headers.get("X-Admin-CSRF")
            or request.headers.get("X-CSRF-Token")
        )
        if not csrf_header:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF protection: state-changing requests require custom header (e.g. X-Requested-With).",
            )

    # 5. Check real-time is_active status in database
    storage = _get_user_storage()
    db_user = None
    try:
        db_user = storage.get_by_id(str(user_id))
    except Exception:
        pass

    if not db_user:
        try:
            db_user = storage.get_by_username(username)
        except Exception:
            pass

    if not db_user and hasattr(storage, "get_admin_by_email") and email:
        try:
            db_user = storage.get_admin_by_email(email)
        except Exception:
            pass

    if db_user is not None and not db_user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account is deactivated or revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        user_id=str(db_user.get("id", user_id)) if db_user else str(user_id),
        username=db_user.get("username", username) if db_user else username,
        role=db_user.get("role", role) if db_user else role,
        email=db_user.get("email", email) if db_user else email,
        name=db_user.get("name") if db_user else username,
        token_jti=token_jti,
    )


async def require_admin_role(
    user: AuthenticatedUser = Depends(get_current_user),
    _rate_limit: None = Depends(rate_limit_guard),
) -> AuthenticatedUser:
    """
    Enforce that the authenticated user possesses the 'admin' role.
    Rejects regular users with 403 Forbidden.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to access this resource",
        )
    return user


async def require_user_role(
    user: AuthenticatedUser = Depends(get_current_user),
    _rate_limit: None = Depends(rate_limit_guard),
) -> AuthenticatedUser:
    """
    Allow any authenticated user (admin or standard user).
    """
    if user.role not in ("admin", "user"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated role required",
        )
    return user


def require_destructive_confirmation(
    confirm: bool = Query(
        False,
        description="Explicit confirmation flag for destructive operations (e.g. ?confirm=true)",
    ),
    x_confirm_destructive: Optional[str] = Header(
        None,
        description="Alternative header confirmation for destructive actions (e.g. 'true')",
    ),
) -> bool:
    """
    Guardrail requiring explicit caller confirmation before executing destructive
    actions (clearing caches, deleting long-term memory reports, etc.).
    """
    confirmed_by_header = (
        x_confirm_destructive is not None
        and x_confirm_destructive.strip().lower() in ("true", "1", "yes")
    )
    if not (confirm or confirmed_by_header):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Destructive operation blocked by safety safeguard. "
                "You must supply ?confirm=true query parameter or 'X-Confirm-Destructive: true' header."
            ),
        )
    return True
