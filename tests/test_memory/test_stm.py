"""
Tests for memory/stm.py.
Requires a real Redis instance running (docker compose up -d redis).
"""

import time

import pytest

from memory.stm import SessionStore  # noqa


@pytest.fixture
def store():
    s = SessionStore(ttl_seconds=60)
    yield s
    # cleanup
    s.delete("test-session")
    s.delete("test-session-ttl")


def test_set_then_get_returns_same_dict(store):
    store.set("test-session", {"topic": "laptops", "step": "search"})
    result = store.get("test-session")
    assert result == {"topic": "laptops", "step": "search"}


def test_get_missing_key_returns_none(store):
    assert store.get("does-not-exist") is None


def test_set_overwrites_cleanly(store):
    store.set("test-session", {"step": "search"})
    store.set("test-session", {"step": "verify"})
    assert store.get("test-session") == {"step": "verify"}


def test_delete_removes_key(store):
    store.set("test-session", {"step": "search"})
    store.delete("test-session")
    assert store.get("test-session") is None


def test_ttl_expires():
    short_store = SessionStore(ttl_seconds=1)
    short_store.set("test-session-ttl", {"step": "search"})
    assert short_store.get("test-session-ttl") is not None
    time.sleep(2)
    assert short_store.get("test-session-ttl") is None
