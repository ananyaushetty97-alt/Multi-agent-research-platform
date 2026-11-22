"""
Semantic cache: if an incoming topic is nearly identical (by meaning) to a
recently cached topic, return the cached report instead of re-running the
whole pipeline.

Stored in Redis (separate from the STM session store) so cache entries expire
on their own TTL, independent of session lifetime and independent of the
permanent long-term memory in Postgres.
"""

import json
import logging
import time
import uuid

import redis

from memory.config import settings
from memory.embeddings import cosine_similarity, embed

log = logging.getLogger("memory.semantic_cache")

CACHE_KEY_PREFIX = "semcache:"


class SemanticCache:
    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        threshold: float | None = None,
        ttl_seconds: int | None = None,
        prefix: str = CACHE_KEY_PREFIX,
    ):
        self._client = redis_client or redis.Redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )
        self._threshold = threshold if threshold is not None else settings.cache_similarity_threshold
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds
        self._prefix = prefix
        self._last_failure_time: float = 0.0
        self._failure_cache_seconds: float = 30.0

    def _is_failing_fast(self) -> bool:
        return (time.time() - self._last_failure_time) < self._failure_cache_seconds

    def _record_failure(self, err: Exception):
        self._last_failure_time = time.time()
        log.warning("SemanticCache Redis failure, entering 30s fast-fail cooldown: %s", err)

    def _record_success(self):
        self._last_failure_time = 0.0

    def _all_entries(self) -> list[dict]:
        """Scan all non-expired cache entries. Fine at dev/small-team scale."""
        if self._is_failing_fast():
            return []
        entries = []
        try:
            for key in self._client.scan_iter(match=f"{self._prefix}*"):
                raw = self._client.get(key)
                if raw is None:
                    continue
                entry = json.loads(raw)
                entry["_redis_key"] = key
                entries.append(entry)
            self._record_success()
        except (redis.ConnectionError, redis.TimeoutError, redis.RedisError) as e:
            self._record_failure(e)
            return []
        return entries

    def lookup(self, topic: str, user_id: str | None = None) -> dict | None:
        """
        Returns the cached report dict if a near-duplicate topic is found
        above the similarity threshold, otherwise None.
        If user_id is provided, only return entries cached for that user or unowned.
        If user_id is None, only return unowned/public entries.
        """
        if self._is_failing_fast():
            return None

        query_vec = embed(topic)
        best_entry = None
        best_score = 0.0

        for entry in self._all_entries():
            # User isolation boundary check
            cached_user_id = entry.get("user_id")
            if user_id is not None:
                if cached_user_id is not None and cached_user_id != str(user_id):
                    continue
            else:
                if cached_user_id is not None:
                    continue

            score = cosine_similarity(query_vec, entry["embedding"])
            if score >= self._threshold and score > best_score:
                best_entry = entry
                best_score = score

        if best_entry is None:
            return None

        return {
            "report": best_entry["report"],
            "matched_topic": best_entry["topic"],
            "similarity": best_score,
            "cached_at": best_entry["cached_at"],
        }

    def store(self, topic: str, report: dict, user_id: str | None = None) -> str | None:
        """
        Cache a report under this topic. Returns the cache entry's id.
        Caller is responsible for only calling this on verified reports.
        """
        if self._is_failing_fast():
            return None

        entry_id = str(uuid.uuid4())
        entry = {
            "id": entry_id,
            "topic": topic,
            "embedding": embed(topic),
            "report": report,
            "user_id": str(user_id) if user_id else None,
            "cached_at": time.time(),
        }
        try:
            self._client.set(
                f"{self._prefix}{entry_id}",
                json.dumps(entry),
                ex=self._ttl,
            )
            self._record_success()
            return entry_id
        except (redis.ConnectionError, redis.TimeoutError, redis.RedisError) as e:
            self._record_failure(e)
            return None

    def invalidate(self, entry_id: str) -> None:
        """
        Remove a specific cache entry immediately. Call this when a claim in
        a cached report is later flagged as false by the Verify agent.
        """
        if self._is_failing_fast():
            return
        try:
            self._client.delete(f"{self._prefix}{entry_id}")
            self._record_success()
        except (redis.ConnectionError, redis.TimeoutError, redis.RedisError) as e:
            self._record_failure(e)

    def clear_all(self) -> None:
        """Wipe the entire cache prefix. Mostly useful for tests."""
        if self._is_failing_fast():
            return
        try:
            for key in self._client.scan_iter(match=f"{self._prefix}*"):
                self._client.delete(key)
            self._record_success()
        except (redis.ConnectionError, redis.TimeoutError, redis.RedisError) as e:
            self._record_failure(e)


if __name__ == "__main__":
    # Quick manual check — run: python -m memory.semantic_cache
    cache = SemanticCache()
    cache.clear_all()

    cache.store(
        topic="best budget laptops for students in 2026",
        report={"summary": "Top picks: Acer Aspire, Lenovo IdeaPad, ASUS Vivobook."},
    )

    near_dup = "cheap laptops worth buying for college students in 2026"
    unrelated = "history of the Roman aqueduct system"

    print("Near-duplicate lookup:", cache.lookup(near_dup))
    print("Unrelated lookup:", cache.lookup(unrelated))
