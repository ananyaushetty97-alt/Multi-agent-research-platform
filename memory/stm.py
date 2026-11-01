"""
Short-term memory (STM): a dict-like session store backed by Redis.
Keyed by session_id. Each session expires automatically after a TTL.
"""

import json

import redis

from memory.config import settings


class SessionStore:
    def __init__(self, redis_client: redis.Redis | None = None, ttl_seconds: int | None = None):
        self._client = redis_client or redis.Redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.stm_ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    def set(self, session_id: str, data: dict) -> None:
        """Store (or overwrite) the session's data, resetting its TTL."""
        self._client.set(self._key(session_id), json.dumps(data), ex=self._ttl)

    def get(self, session_id: str) -> dict | None:
        """Return the session's data, or None if it doesn't exist / has expired."""
        raw = self._client.get(self._key(session_id))
        if raw is None:
            return None
        return json.loads(raw)

    def delete(self, session_id: str) -> None:
        """Remove a session immediately."""
        self._client.delete(self._key(session_id))

    def exists(self, session_id: str) -> bool:
        return self._client.exists(self._key(session_id)) == 1

    def ping(self) -> bool:
        """Health check — returns True if Redis is reachable."""
        return self._client.ping()


if __name__ == "__main__":
    # Quick manual check — run: python -m memory.stm
    store = SessionStore()
    print("Redis reachable:", store.ping())
    store.set("demo-session", {"topic": "budget laptops", "step": "search"})
    print("Read back:", store.get("demo-session"))
    store.delete("demo-session")
    print("After delete:", store.get("demo-session"))
