import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Dict, Deque, Tuple, Optional
from fastapi import Request

from admin_backend.security.passwords import hash_password, verify_password
from user_auth.config import settings

# Startup generation of dummy PBKDF2 hash for timing attack defense (Condition 3)
DUMMY_HASH: str = hash_password(secrets.token_hex(16))


def generate_session_token() -> str:
    """Generate cryptographically secure 256-bit random opaque token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Compute SHA-256 hex digest of the raw session token for storage and lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_client_ip(request: Request) -> str:
    """
    Extract client IP. Do NOT trust X-Forwarded-For unless TRUSTED_PROXY=true (Condition 10).
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
    Thread-safe rate limiting and account lockout manager (Condition 10).
    - IP Rate Limiting: 10 requests/minute per client IP.
    - Account Lockout: 5 consecutive failed attempts per (email, IP) -> 5 minute cooldown.
    - Applies to all failed attempts, including nonexistent emails.
    """
    def __init__(self, ip_limit: int = 10, lockout_threshold: int = 5, lockout_duration_seconds: int = 300):
        self.ip_limit = ip_limit
        self.window_seconds = 60.0
        self.lockout_threshold = lockout_threshold
        self.lockout_duration_seconds = lockout_duration_seconds

        self._ip_requests: Dict[str, Deque[float]] = defaultdict(deque)
        # Key: (normalized_email, client_ip) -> list of failure timestamps
        self._failed_attempts: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check_ip_rate_limit(self, client_ip: str) -> bool:
        """Sliding-window IP rate limit. Returns True if allowed, False if exceeded."""
        if not client_ip or client_ip in ("testclient", "127.0.0.1", "localhost", "::1"):
            # Still track localhost in production, but allow tests to run cleanly
            pass

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
        """Check if (email, client_ip) is currently locked out. Returns (is_locked, remaining_seconds)."""
        key = (email.strip().lower(), client_ip)
        now = time.time()
        with self._lock:
            q = self._failed_attempts[key]
            # Remove failures older than lockout window
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
            if key in self._failed_attempts:
                self._failed_attempts[key].clear()

    def reset(self) -> None:
        """Clear all states (used by unit tests)."""
        with self._lock:
            self._ip_requests.clear()
            self._failed_attempts.clear()


auth_security_manager = RateLimiterAndLockoutManager()
