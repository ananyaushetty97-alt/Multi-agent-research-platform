"""
Tests for memory/ltm.py.
Requires a real Postgres+pgvector instance running (docker compose up -d postgres).
"""

import pytest

from memory.embeddings import embed
from memory.ltm import LongTermMemory


@pytest.fixture
def ltm():
    store = LongTermMemory()
    store.init_schema()
    yield store
    # no teardown needed — each test uses fresh unique report_ids implicitly


def test_store_and_find_similar_returns_closest_match(ltm):
    laptop_id = ltm.store_report(
        text="Best budget laptops for students in 2026",
        embedding=embed("Best budget laptops for students in 2026"),
        metadata={"test": True},
    )
    ltm.store_report(
        text="History of the Roman aqueduct system",
        embedding=embed("History of the Roman aqueduct system"),
        metadata={"test": True},
    )

    query = "cheap laptops recommended for college students"
    results = ltm.find_similar(embed(query), top_k=1)

    assert len(results) == 1
    assert results[0]["id"] == laptop_id
    assert results[0]["similarity"] > 0.5

    ltm.delete_report(laptop_id)


def test_find_similar_on_empty_query_topic(ltm):
    query = "a completely unrelated niche topic about deep sea fish migration"
    results = ltm.find_similar(embed(query), top_k=3)
    # Should not error even if nothing matches well — just returns whatever exists
    assert isinstance(results, list)
