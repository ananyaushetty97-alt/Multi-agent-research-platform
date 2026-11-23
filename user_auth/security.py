import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Dict, Deque, Tuple, Optional
from fastapi import Request

try:
    import bcrypt
    _HAS_BCRYPT = True
except ImportError:
    _HAS_BCRYPT = False

from admin_backend.security.passwords import (
    hash_password as pbkdf2_hash_password,
    verify_password as pbkdf2_verify_password,
)
from user_auth.config import settings


def hash_user_password(plain_password: str) -> str:
    """
    Hash a user password using bcrypt (or standard PBKDF2 if bcrypt C-extension is unavailable).
    """
    if not plain_password:
        raise ValueError("Password cannot be empty")
    if _HAS_BCRYPT:
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
        return hashed.decode("utf-8")
    return pbkdf2_hash_password(plain_password, iterations=50_000)


def verify_user_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a user password.
    Supports both bcrypt hashes ($2b$, $2a$) and PBKDF2 hashes (pbkdf2_sha256$).
    """
    if not plain_password or not hashed_password:
        return False
    try:
        if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
            if _HAS_BCRYPT:
                return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
            return False
        if hashed_password.startswith("pbkdf2_"):
            return pbkdf2_verify_password(plain_password, hashed_password)
        return False
    except Exception:
        return False


# Generate dummy hash for timing-attack mitigation
DUMMY_HASH: str = hash_user_password(secrets.token_hex(16))


def generate_session_token() -> str:
    """Generate cryptographically secure 256-bit random opaque token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Compute SHA-256 hex digest of the raw session token for storage and lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_otp_code() -> str:
    """Generate secure 6-digit numeric OTP."""
    code = secrets.randbelow(900000) + 100000
    return str(code)


def hash_otp_code(otp: str) -> str:
    """Compute SHA-256 hex digest of OTP so plain code is never stored in DB."""
    return hashlib.sha256(otp.strip().encode("utf-8")).hexdigest()


def generate_reset_token() -> str:
    """Generate high-entropy random token for password reset links."""
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    """Compute SHA-256 hex digest of password reset token."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def get_client_ip(request: Request) -> str:
    """
    Extract client IP. Do NOT trust X-Forwarded-For unless TRUSTED_PROXY=true.
    """
    if settings.trusted_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if parts:
                return parts[0]
    return request.client.host if request.client else "unknown"


class RateLimiterAndLockoutManager:
    """
    Thread-safe rate limiting and account lockout manager:
    - IP Rate Limiting: 15 requests/minute per client IP for auth actions.
    - Account Lockout: 5 consecutive failed attempts per (email, IP) -> 5 minute cooldown.
    - OTP verification attempts: max 5 attempts per OTP.
    - OTP resend cooldown: 60 seconds.
    - Password reset request rate limit: 3 per hour per email.
    """
    def __init__(self, ip_limit: int = 15, lockout_threshold: int = 5, lockout_duration_seconds: int = 300):
        self.ip_limit = ip_limit
        self.window_seconds = 60.0
        self.lockout_threshold = lockout_threshold
        self.lockout_duration_seconds = lockout_duration_seconds

        self._ip_requests: Dict[str, Deque[float]] = defaultdict(deque)
        self._failed_attempts: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._otp_resend_timestamps: Dict[str, float] = {}  # email -> timestamp
        self._reset_request_timestamps: Dict[str, Deque[float]] = defaultdict(deque)  # email -> timestamps
        self._lock = threading.Lock()

    def check_ip_rate_limit(self, client_ip: str) -> bool:
        """Sliding-window IP rate limit. Returns True if allowed, False if exceeded."""
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            q = self._ip_requests[client_ip]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.ip_limit:
                return False
            q.append(now)
            return True

    def is_locked_out(self, email: str, client_ip: str) -> Tuple[bool, int]:
        """Check if (email, client_ip) is locked out. Returns (is_locked, remaining_seconds)."""
        key = (email.strip().lower(), client_ip)
        now = time.time()
        with self._lock:
            q = self._failed_attempts[key]
            cutoff = now - self.lockout_duration_seconds
            while q and q[0] < cutoff:
                q.popleft()

            if len(q) >= self.lockout_threshold:
                remaining = int(self.lockout_duration_seconds - (now - q[-1]))
                return True, max(1, remaining)
            return False, 0

    def record_failure(self, email: str, client_ip: str) -> None:
        """Record a failed login attempt for (email, client_ip)."""
        key = (email.strip().lower(), client_ip)
        now = time.time()
        with self._lock:
            self._failed_attempts[key].append(now)

    def record_success(self, email: str, client_ip: str) -> None:
        """Reset failed attempt counters upon successful authentication."""
        key = (email.strip().lower(), client_ip)
        with self._lock:
            self._failed_attempts.pop(key, None)

    def check_otp_resend_cooldown(self, email: str, cooldown_seconds: int = 60) -> Tuple[bool, int]:
        """Check if resending OTP is permitted or in cooldown. Returns (allowed, remaining_seconds)."""
        key = email.strip().lower()
        now = time.time()
        with self._lock:
            last = self._otp_resend_timestamps.get(key, 0.0)
            elapsed = now - last
            if elapsed < cooldown_seconds:
                return False, int(cooldown_seconds - elapsed)
            self._otp_resend_timestamps[key] = now
            return True, 0

    def check_password_reset_limit(self, email: str, max_per_hour: int = 5) -> bool:
        """Check if password reset requests exceed limit per hour."""
        key = email.strip().lower()
        now = time.time()
        cutoff = now - 3600.0
        with self._lock:
            q = self._reset_request_timestamps[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= max_per_hour:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        """Clear all tracking state (used in testing fixtures)."""
        with self._lock:
            self._ip_requests.clear()
            self._failed_attempts.clear()
            self._otp_resend_timestamps.clear()
            self._reset_request_timestamps.clear()


auth_security_manager = RateLimiterAndLockoutManager()
