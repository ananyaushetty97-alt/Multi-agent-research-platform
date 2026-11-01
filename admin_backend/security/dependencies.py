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
    def __init__(self, user_id: str, username: str, role: str):
        self.user_id = user_id
        self.username = username
        self.role = role

    def is_admin(self) -> bool:
        return self.role == "admin"


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> AuthenticatedUser:
    """
    Extract and validate JWT Bearer token from Authorization header.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
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
    role = payload.get("role", "user")

    if not user_id or not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(user_id=str(user_id), username=username, role=role)


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
