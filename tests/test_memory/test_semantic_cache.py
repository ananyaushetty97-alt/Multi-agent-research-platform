"""
Tests for memory/semantic_cache.py.
Requires a real Redis instance running (docker compose up -d redis).
"""

import pytest

from memory.semantic_cache import SemanticCache


@pytest.fixture
def cache():
    c = SemanticCache(threshold=0.80, ttl_seconds=60)
    c.clear_all()
    yield c
    c.clear_all()


def test_near_duplicate_topic_is_a_hit(cache):
    cache.store(
        topic="best budget laptops for students in 2026",
        report={"summary": "Acer, Lenovo, ASUS picks"},
    )
    result = cache.lookup("cheap laptops worth buying for college students in 2026")
    assert result is not None
    assert result["report"]["summary"] == "Acer, Lenovo, ASUS picks"


def test_unrelated_topic_is_a_miss(cache):
    cache.store(
        topic="best budget laptops for students in 2026",
        report={"summary": "Acer, Lenovo, ASUS picks"},
    )
    result = cache.lookup("history of the Roman aqueduct system")
    assert result is None


def test_invalidate_removes_entry(cache):
    entry_id = cache.store(
        topic="best budget laptops for students in 2026",
        report={"summary": "Acer, Lenovo, ASUS picks"},
    )
    cache.invalidate(entry_id)
    result = cache.lookup("best budget laptops for students in 2026")
    assert result is None
