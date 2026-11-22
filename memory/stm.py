"""
Short-term memory (STM): a dict-like session store backed by Redis.
Keyed by session_id. Each session expires automatically after a TTL.
"""

import json
import logging
import threading
import time

import redis

from memory.config import settings

log = logging.getLogger("memory.stm")


class SessionStore:
    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        ttl_seconds: int | None = None,
        prefix: str = "session:",
    ):
        self._client = redis_client or redis.Redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.stm_ttl_seconds
        self._prefix = prefix
        self._fallback_store: dict[str, tuple[dict, float]] = {}  # key -> (data, expires_at)
        self._fallback_lock = threading.Lock()

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def _fallback_set(self, key: str, data: dict) -> None:
        with self._fallback_lock:
            expires_at = time.time() + self._ttl
            self._fallback_store[key] = (data, expires_at)

    def _fallback_get(self, key: str) -> dict | None:
        with self._fallback_lock:
            entry = self._fallback_store.get(key)
            if entry is None:
                return None
            data, expires_at = entry
            if time.time() > expires_at:
                del self._fallback_store[key]
                return None
            return data

    def _fallback_delete(self, key: str) -> None:
        with self._fallback_lock:
            self._fallback_store.pop(key, None)

    def _fallback_exists(self, key: str) -> bool:
        return self._fallback_get(key) is not None

    def set(self, session_id: str, data: dict) -> None:
        """Store (or overwrite) the session's data, resetting its TTL. Falls back to in-memory store on Redis outage."""
        key = self._key(session_id)
        try:
            self._client.set(key, json.dumps(data), ex=self._ttl)
        except (redis.ConnectionError, redis.TimeoutError, redis.RedisError) as e:
            log.warning("Redis unavailable in SessionStore.set, falling back to in-memory store: %s", e)
            self._fallback_set(key, data)

    def get(self, session_id: str) -> dict | None:
        """Return the session's data, or None if it doesn't exist / has expired. Falls back to in-memory store on Redis outage."""
        key = self._key(session_id)
        try:
            raw = self._client.get(key)
            if raw is None:
                return self._fallback_get(key)
            return json.loads(raw)
        except (redis.ConnectionError, redis.TimeoutError, redis.RedisError) as e:
            log.warning("Redis unavailable in SessionStore.get, falling back to in-memory store: %s", e)
            return self._fallback_get(key)

    def delete(self, session_id: str) -> None:
        """Remove a session immediately."""
        key = self._key(session_id)
        try:
            self._client.delete(key)
        except (redis.ConnectionError, redis.TimeoutError, redis.RedisError) as e:
            log.warning("Redis unavailable in SessionStore.delete, falling back to in-memory store: %s", e)
        finally:
            self._fallback_delete(key)

    def exists(self, session_id: str) -> bool:
        key = self._key(session_id)
        try:
            return bool(self._client.exists(key) == 1) or self._fallback_exists(key)
        except (redis.ConnectionError, redis.TimeoutError, redis.RedisError) as e:
            log.warning("Redis unavailable in SessionStore.exists, falling back to in-memory store: %s", e)
            return self._fallback_exists(key)

    def ping(self) -> bool:
        """Health check — returns True if Redis is reachable."""
        try:
            return bool(self._client.ping())
        except Exception:
            return False


if __name__ == "__main__":
    # Quick manual check — run: python -m memory.stm
    store = SessionStore()
    print("Redis reachable:", store.ping())
    store.set("demo-session", {"topic": "budget laptops", "step": "search"})
    print("Read back:", store.get("demo-session"))
    store.delete("demo-session")
    print("After delete:", store.get("demo-session"))
