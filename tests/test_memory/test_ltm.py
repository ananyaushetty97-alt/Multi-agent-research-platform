"""
Tests for memory/ltm.py.
Works with real Postgres+pgvector or tests circuit breaker fast-fail.
"""

import pytest
import psycopg

from memory.config import settings
from memory.embeddings import embed
from memory.ltm import LongTermMemory


def is_postgres_available() -> bool:
    try:
        with psycopg.connect(settings.postgres_dsn, connect_timeout=1) as conn:
            return True
    except Exception:
        return False


postgres_available = is_postgres_available()


@pytest.fixture
def ltm():
    # Use isolated test table 'test_reports' — never delete or touch production 'reports'
    store = LongTermMemory(table_name="test_reports")
    store.init_schema()
    yield store
    # Teardown: drop isolated test table cleanly
    try:
        with store._connect(register_vector_type=False) as conn:
            conn.execute("DROP TABLE IF EXISTS test_reports CASCADE")
            conn.commit()
    except Exception:
        pass


@pytest.mark.skipif(not postgres_available, reason="PostgreSQL/pgvector is not reachable")
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
    assert str(results[0]["id"]) == laptop_id
    assert results[0]["similarity"] > 0.5

    ltm.delete_report(laptop_id)


@pytest.mark.skipif(not postgres_available, reason="PostgreSQL/pgvector is not reachable")
def test_find_similar_on_empty_query_topic(ltm):
    query = "a completely unrelated niche topic about deep sea fish migration"
    results = ltm.find_similar(embed(query), top_k=3)
    # Should not error even if nothing matches well — just returns whatever exists
    assert isinstance(results, list)


def test_ltm_circuit_breaker_fast_fail():
    """Verify that when PostgreSQL connection fails, LTM trips a circuit breaker and fails fast."""
    # Point to an invalid unreachable port
    store = LongTermMemory(dsn="postgresql://postgres:fake@127.0.0.1:54329/nonexistent")
    # First attempt fails after connection attempt
    with pytest.raises(psycopg.OperationalError):
        store._connect()

    assert store._last_failure_time > 0

    # Second immediate attempt trips circuit breaker instantly without network attempt
    import time
    t0 = time.perf_counter()
    with pytest.raises(psycopg.OperationalError) as exc_info:
        store._connect()
    dt = time.perf_counter() - t0
    assert dt < 0.1  # Fast fail in <100ms
    assert "fast-fail circuit breaker" in str(exc_info.value)
