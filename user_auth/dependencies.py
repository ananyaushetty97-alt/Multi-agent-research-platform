import logging
from urllib.parse import urlparse
from typing import Optional
from fastapi import Request, HTTPException, Depends, status

from user_auth.config import settings
from user_auth.models import UserResponse
from user_auth.service import auth_service

log = logging.getLogger("user_auth.dependencies")


def require_csrf_protection(request: Request) -> None:
    """
    Enforce multi-layer CSRF defense on state-changing endpoints (Condition 6):
    1. Custom Header: Requires 'X-Requested-With: XMLHttpRequest'.
    2. Origin / Host verification: Origin header, if present, must match Host or ALLOWED_AUTH_HOSTS.
    """
    # 1. Custom Header Check
    x_requested = request.headers.get("x-requested-with")
    if not x_requested or x_requested.strip().lower() != "xmlhttprequest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF protection: Missing or invalid X-Requested-With header",
        )

    # 2. Origin / Host Check
    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlparse(origin)
            origin_host = parsed.netloc.lower()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF protection: Malformed Origin header",
            )

        current_host = request.headers.get("host", "").strip().lower()
        allowed_hosts = set(settings.get_allowed_hosts())
        if current_host:
            allowed_hosts.add(current_host)

        if origin_host not in allowed_hosts:
            log.warning(f"CSRF Origin mismatch: origin '{origin_host}' not in allowed hosts {allowed_hosts}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF protection: Origin mismatch",
            )


def get_current_user(request: Request) -> UserResponse:
    """
    Strict dependency requiring a valid, active regular user session cookie.
    Raises 401 if unauthenticated.
    """
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    user = auth_service.get_user_from_session_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    return user


def require_verified_user(user: UserResponse = Depends(get_current_user)) -> UserResponse:
    """
    Enforce that authenticated user has completed email verification.
    Unverified accounts cannot access protected features or chat.
    """
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required. Please verify your email before accessing research features.",
        )
    return user


def get_optional_user(request: Request) -> Optional[UserResponse]:
    """
    Optional user dependency for guest / user hybrid endpoints (Condition 9 & 11).
    - If cookie is missing or invalid: logs swallowed exception and returns None (guest).
    - If REQUIRE_LOGIN=true and storage is down: returns 503 instead of 401.
    """
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        if settings.require_login:
            # Check if storage is down to return 503 instead of 401 (Condition 9)
            try:
                auth_service.storage.get_user_by_id("00000000-0000-0000-0000-000000000000")
            except HTTPException as e:
                if e.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
                    raise e
            except Exception as e:
                log.warning(f"Storage probe failed in get_optional_user: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service temporarily unavailable",
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        return None

    try:
        user = auth_service.get_user_from_session_token(token)
        if user:
            return user
        if settings.require_login:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or invalid",
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        log.warning(f"Swallowed exception in get_optional_user: {e}", exc_info=True)
        if settings.require_login:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            )
        return None
