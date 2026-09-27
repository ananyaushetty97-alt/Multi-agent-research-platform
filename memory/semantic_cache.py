"""
Semantic cache: if an incoming topic is nearly identical (by meaning) to a
recently cached topic, return the cached report instead of re-running the
whole pipeline.

Stored in Redis (separate from the STM session store) so cache entries expire
on their own TTL, independent of session lifetime and independent of the
permanent long-term memory in Postgres.
"""

import json
import time
import uuid

import redis

from memory.config import settings
from memory.embeddings import cosine_similarity, embed

CACHE_KEY_PREFIX = "semcache:"


class SemanticCache:
    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        threshold: float | None = None,
        ttl_seconds: int | None = None,
    ):
        self._client = redis_client or redis.Redis.from_url(
            settings.redis_url, decode_responses=True
        )
        self._threshold = threshold if threshold is not None else settings.cache_similarity_threshold
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds

    def _all_entries(self) -> list[dict]:
        """Scan all non-expired cache entries. Fine at dev/small-team scale."""
        entries = []
        for key in self._client.scan_iter(match=f"{CACHE_KEY_PREFIX}*"):
            raw = self._client.get(key)
            if raw is None:
                continue
            entry = json.loads(raw)
            entry["_redis_key"] = key
            entries.append(entry)
        return entries

    def lookup(self, topic: str) -> dict | None:
        """
        Returns the cached report dict if a near-duplicate topic is found
        above the similarity threshold, otherwise None.
        Only reports marked status="verified" should ever be stored here
        (enforce that at the call site, in the pipeline).
        """
        query_vec = embed(topic)
        best_entry = None
        best_score = 0.0

        for entry in self._all_entries():
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

    def store(self, topic: str, report: dict) -> str:
        """
        Cache a report under this topic. Returns the cache entry's id.
        Caller is responsible for only calling this on verified reports.
        """
        entry_id = str(uuid.uuid4())
        entry = {
            "id": entry_id,
            "topic": topic,
            "embedding": embed(topic),
            "report": report,
            "cached_at": time.time(),
        }
        self._client.set(
            f"{CACHE_KEY_PREFIX}{entry_id}",
            json.dumps(entry),
            ex=self._ttl,
        )
        return entry_id

    def invalidate(self, entry_id: str) -> None:
        """
        Remove a specific cache entry immediately. Call this when a claim in
        a cached report is later flagged as false by the Verify agent.
        """
        self._client.delete(f"{CACHE_KEY_PREFIX}{entry_id}")

    def clear_all(self) -> None:
        """Wipe the entire cache. Mostly useful for tests."""
        for key in self._client.scan_iter(match=f"{CACHE_KEY_PREFIX}*"):
            self._client.delete(key)


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
