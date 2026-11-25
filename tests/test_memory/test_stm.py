"""
Tests for memory/stm.py.
Works with real Redis if available, or verifies in-memory fallback.
"""

import time
import pytest
import redis
from unittest.mock import MagicMock

from memory.config import settings
from memory.stm import SessionStore


def is_redis_available() -> bool:
    try:
        r = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        return bool(r.ping())
    except Exception:
        return False


redis_available = is_redis_available()


@pytest.fixture
def store():
    s = SessionStore(ttl_seconds=60, prefix="test_session:")
    yield s
    # cleanup
    s.delete("test-session")
    s.delete("test-session-ttl")


@pytest.mark.skipif(not redis_available, reason="Live Redis is not reachable")
def test_set_then_get_returns_same_dict(store):
    store.set("test-session", {"topic": "laptops", "step": "search"})
    result = store.get("test-session")
    assert result == {"topic": "laptops", "step": "search"}


@pytest.mark.skipif(not redis_available, reason="Live Redis is not reachable")
def test_get_missing_key_returns_none(store):
    assert store.get("does-not-exist") is None


@pytest.mark.skipif(not redis_available, reason="Live Redis is not reachable")
def test_set_overwrites_cleanly(store):
    store.set("test-session", {"step": "search"})
    store.set("test-session", {"step": "verify"})
    assert store.get("test-session") == {"step": "verify"}


@pytest.mark.skipif(not redis_available, reason="Live Redis is not reachable")
def test_delete_removes_key(store):
    store.set("test-session", {"step": "search"})
    store.delete("test-session")
    assert store.get("test-session") is None


@pytest.mark.skipif(not redis_available, reason="Live Redis is not reachable")
def test_ttl_expires():
    short_store = SessionStore(ttl_seconds=1, prefix="test_session:")
    short_store.set("test-session-ttl", {"step": "search"})
    assert short_store.get("test-session-ttl") is not None
    time.sleep(2)
    assert short_store.get("test-session-ttl") is None


def test_stm_in_memory_fallback_when_redis_down():
    """Verify that when Redis raises ConnectionError/TimeoutError, STM continues working via in-memory dict."""
    failing_client = MagicMock()
    failing_client.set.side_effect = redis.ConnectionError("Simulated Redis outage")
    failing_client.get.side_effect = redis.ConnectionError("Simulated Redis outage")
    failing_client.exists.side_effect = redis.TimeoutError("Simulated Redis timeout")
    failing_client.delete.side_effect = redis.ConnectionError("Simulated Redis outage")
    failing_client.ping.side_effect = redis.ConnectionError("Simulated Redis outage")

    fallback_store = SessionStore(redis_client=failing_client, ttl_seconds=2, prefix="fallback_test:")
    assert fallback_store.ping() is False

    # set then get works seamlessly without raising
    fallback_store.set("offline-session", {"topic": "quantum", "offline": True})
    assert fallback_store.exists("offline-session") is True
    res = fallback_store.get("offline-session")
    assert res == {"topic": "quantum", "offline": True}

    # delete works
    fallback_store.delete("offline-session")
    assert fallback_store.get("offline-session") is None
    assert fallback_store.exists("offline-session") is False
