"""
Thread-safe rate limiting hook for admin endpoints.
Maintains a sliding-window counter per client (IP address or authenticated user).
"""
import time
import threading
from collections import defaultdict, deque
from typing import Dict, Deque
from fastapi import Request, HTTPException, status

from admin_backend.config import settings


class InMemoryRateLimiter:
    def __init__(self, requests_per_minute: int | None = None):
        self.limit = requests_per_minute or settings.admin_rate_limit_per_minute
        self.window_seconds = 60
        self._requests: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_allowed(self, client_key: str) -> tuple[bool, int]:
        """
        Check if a request is allowed. Returns (allowed, remaining_quota).
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._requests[client_key]
            # Evict timestamps older than the window
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.limit:
                return False, 0

            timestamps.append(now)
            remaining = self.limit - len(timestamps)
            return True, remaining

    def reset(self):
        """Reset rate limiter state (useful for tests)."""
        with self._lock:
            self._requests.clear()


# Global rate limiter instance
admin_rate_limiter = InMemoryRateLimiter()


def rate_limit_guard(request: Request):
    """
    FastAPI dependency hook to enforce rate limits on admin endpoints.
    """
    client_ip = request.client.host if request.client else "unknown"
    allowed, remaining = admin_rate_limiter.is_allowed(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {admin_rate_limiter.limit} requests per minute."
        )
