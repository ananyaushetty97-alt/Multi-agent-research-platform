from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from user_auth.config import settings
from user_auth.dependencies import require_csrf_protection, get_current_user
from user_auth.models import (
    UserRegisterRequest,
    UserLoginRequest,
    GoogleLoginRequest,
    VerifyOtpRequest,
    ResendOtpRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserResponse,
    AuthConfigResponse,
)
from user_auth.security import get_client_ip, auth_security_manager
from user_auth.service import auth_service

router = APIRouter(tags=["User Auth"])


def _set_session_cookie(response: Response, raw_token: str) -> None:
    """Helper to attach the secure session cookie."""
    max_age_seconds = settings.session_cookie_max_age_days * 86400
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    """Helper to clear the session cookie on logout."""
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


@router.post(
    "/register",
    response_model=UserResponse,
    dependencies=[Depends(require_csrf_protection)],
)
def register(req: UserRegisterRequest, request: Request, response: Response):
    client_ip = get_client_ip(request)
    if not auth_security_manager.check_ip_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait a minute before making further registration requests.",
        )

    user_agent = request.headers.get("user-agent")
    user, raw_token = auth_service.register(req, client_ip=client_ip, user_agent=user_agent)
    if raw_token:
        _set_session_cookie(response, raw_token)
    return user


@router.post(
    "/login",
    response_model=UserResponse,
    dependencies=[Depends(require_csrf_protection)],
)
def login(req: UserLoginRequest, request: Request, response: Response):
    client_ip = get_client_ip(request)
    if not auth_security_manager.check_ip_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait a minute before making further login requests.",
        )

    user_agent = request.headers.get("user-agent")
    user, raw_token = auth_service.login(req, client_ip=client_ip, user_agent=user_agent)
    _set_session_cookie(response, raw_token)
    return user


@router.post(
    "/logout",
    dependencies=[Depends(require_csrf_protection)],
)
def logout(request: Request, response: Response) -> Dict[str, str]:
    client_ip = get_client_ip(request)
    raw_token = request.cookies.get(settings.session_cookie_name)
    auth_service.logout(raw_token, client_ip=client_ip)
    _clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(user: UserResponse = Depends(get_current_user)):
    return user


@router.post(
    "/google",
    response_model=UserResponse,
    dependencies=[Depends(require_csrf_protection)],
)
def google_login(req: GoogleLoginRequest, request: Request, response: Response):
    client_ip = get_client_ip(request)
    if not auth_security_manager.check_ip_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait a minute before making further login requests.",
        )

    user_agent = request.headers.get("user-agent")
    user, raw_token = auth_service.google_login(req, client_ip=client_ip, user_agent=user_agent)
    _set_session_cookie(response, raw_token)
    return user


@router.post(
    "/verify-otp",
    dependencies=[Depends(require_csrf_protection)],
)
def verify_otp(req: VerifyOtpRequest, request: Request, response: Response) -> Dict[str, Any]:
    """Verify email via 6-digit OTP."""
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent")
    result = auth_service.verify_otp(req, client_ip=client_ip, user_agent=user_agent)
    if result.get("raw_token"):
        _set_session_cookie(response, result["raw_token"])
    return result


@router.get("/verify")
def verify_link(token: str, email: Optional[str] = None, request: Request = None):
    """Verify email via single-use magic link and redirect to dashboard."""
    client_ip = get_client_ip(request) if request else "unknown"
    user_agent = request.headers.get("user-agent") if request else None
    res = auth_service.verify_token(token=token, email=email, client_ip=client_ip, user_agent=user_agent)
    # Redirect to user UI with verified query parameter and set session cookie
    redirect_resp = RedirectResponse(url="/user/index.html?verified=true", status_code=status.HTTP_302_FOUND)
    if res.get("raw_token"):
        _set_session_cookie(redirect_resp, res["raw_token"])
    return redirect_resp


@router.post(
    "/resend-otp",
    dependencies=[Depends(require_csrf_protection)],
)
def resend_otp(req: ResendOtpRequest, request: Request) -> Dict[str, Any]:
    """Resend 6-digit verification code with 60s cooldown."""
    client_ip = get_client_ip(request)
    return auth_service.resend_otp(req, client_ip=client_ip)


@router.post(
    "/forgot-password",
    dependencies=[Depends(require_csrf_protection)],
)
def forgot_password(req: ForgotPasswordRequest, request: Request) -> Dict[str, Any]:
    """Request password reset link."""
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent")
    return auth_service.request_password_reset(req, client_ip=client_ip, user_agent=user_agent)


@router.post(
    "/reset-password",
    dependencies=[Depends(require_csrf_protection)],
)
def reset_password(req: ResetPasswordRequest, request: Request, response: Response) -> Dict[str, Any]:
    """Reset password using one-time token."""
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent")
    res = auth_service.reset_password(req, client_ip=client_ip, user_agent=user_agent)
    # Clear any active session cookie on password reset
    _clear_session_cookie(response)
    return res


@router.get("/config", response_model=AuthConfigResponse)
def get_auth_config():
    """Public configuration endpoint exposing Google Client ID."""
    return AuthConfigResponse(google_client_id=settings.google_client_id)
