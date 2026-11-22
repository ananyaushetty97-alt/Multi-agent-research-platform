"""
Tests for memory/semantic_cache.py.
Works with real Redis or tests circuit breaker fast-fail.
"""

import pytest
import redis
from unittest.mock import MagicMock

from memory.config import settings
from memory.semantic_cache import SemanticCache


def is_redis_available() -> bool:
    try:
        r = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        return bool(r.ping())
    except Exception:
        return False


redis_available = is_redis_available()


@pytest.fixture
def cache():
    c = SemanticCache(threshold=0.80, ttl_seconds=60, prefix="semcache:test:")
    c.clear_all()
    yield c
    c.clear_all()


@pytest.mark.skipif(not redis_available, reason="Live Redis is not reachable")
def test_near_duplicate_topic_is_a_hit(cache):
    cache.store(
        topic="best budget laptops for students in 2026",
        report={"summary": "Acer, Lenovo, ASUS picks"},
    )
    result = cache.lookup("cheap laptops worth buying for college students in 2026")
    assert result is not None
    assert result["report"]["summary"] == "Acer, Lenovo, ASUS picks"


@pytest.mark.skipif(not redis_available, reason="Live Redis is not reachable")
def test_unrelated_topic_is_a_miss(cache):
    cache.store(
        topic="best budget laptops for students in 2026",
        report={"summary": "Acer, Lenovo, ASUS picks"},
    )
    result = cache.lookup("history of the Roman aqueduct system")
    assert result is None


@pytest.mark.skipif(not redis_available, reason="Live Redis is not reachable")
def test_invalidate_removes_entry(cache):
    entry_id = cache.store(
        topic="best budget laptops for students in 2026",
        report={"summary": "Acer, Lenovo, ASUS picks"},
    )
    cache.invalidate(entry_id)
    result = cache.lookup("best budget laptops for students in 2026")
    assert result is None


def test_semantic_cache_circuit_breaker_fast_fail():
    """Verify that when Redis is down, SemanticCache fails fast without stalling and returns None."""
    failing_client = MagicMock()
    failing_client.scan_iter.side_effect = redis.ConnectionError("Redis down")
    failing_client.set.side_effect = redis.ConnectionError("Redis down")

    c = SemanticCache(redis_client=failing_client, prefix="semcache:down_test:")
    # First attempt encounters error and triggers circuit breaker
    res = c.lookup("best budget laptops")
    assert res is None
    assert c._is_failing_fast() is True

    # Subsequent lookup returns None immediately without querying client
    failing_client.scan_iter.reset_mock()
    res2 = c.lookup("best budget laptops")
    assert res2 is None
    failing_client.scan_iter.assert_not_called()
