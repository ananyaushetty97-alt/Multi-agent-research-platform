"""
Long-term memory (LTM): stores finished reports with their embeddings in
Postgres (pgvector extension), and retrieves similar past reports later.
"""

import json
import time
import uuid
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from pgvector.psycopg import register_vector

from memory.config import settings

EMBEDDING_DIM = 384  # matches all-MiniLM-L6-v2's output size; change if you swap models

CREATE_TABLE_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY,
    text TEXT NOT NULL,
    embedding VECTOR({EMBEDDING_DIM}) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS reports_embedding_idx
    ON reports USING hnsw (embedding vector_cosine_ops);
"""


class LongTermMemory:
    def __init__(self, dsn: str | None = None, table_name: str = "reports"):
        if not table_name.isidentifier():
            raise ValueError(f"Invalid table name: {table_name}")
        self._dsn = dsn or settings.postgres_dsn
        self.table_name = table_name
        self._last_failure_time: float = 0.0
        self._failure_cache_seconds: float = 30.0

    def _connect(self, register_vector_type: bool = True) -> psycopg.Connection:
        now = time.time()
        if (now - self._last_failure_time) < self._failure_cache_seconds:
            raise psycopg.OperationalError(
                f"LTM fast-fail circuit breaker: connection recently failed ({now - self._last_failure_time:.1f}s ago < {self._failure_cache_seconds}s)"
            )

        try:
            conn = psycopg.connect(self._dsn, connect_timeout=2, row_factory=dict_row)
            if register_vector_type:
                register_vector(conn)
            self._last_failure_time = 0.0
            return conn
        except Exception:
            self._last_failure_time = time.time()
            raise

    def init_schema(self) -> None:
        """
        Run once (or every startup — it's idempotent) to ensure the extension
        and table exist. Uses a plain connection (register_vector_type=False)
        because the 'vector' type doesn't exist in a brand-new database until
        CREATE EXTENSION runs here — registering it any earlier would fail.
        """
        schema_sql = f"""
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE IF NOT EXISTS {self.table_name} (
            id UUID PRIMARY KEY,
            text TEXT NOT NULL,
            embedding VECTOR({EMBEDDING_DIM}) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS {self.table_name}_embedding_idx
            ON {self.table_name} USING hnsw (embedding vector_cosine_ops);
        """
        with self._connect(register_vector_type=False) as conn:
            conn.execute(schema_sql)
            conn.commit()

    def store_report(
        self,
        text: str,
        embedding: list[float],
        metadata: dict | None = None,
        report_id: str | None = None,
    ) -> str:
        """Save a verified report. Returns the report's id."""
        report_id = report_id or str(uuid.uuid4())
        metadata = metadata or {}
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self.table_name} (id, text, embedding, metadata, created_at)
                VALUES (%s, %s, %s::vector, %s, %s)
                """,
                (report_id, text, embedding, json.dumps(metadata), datetime.now(timezone.utc)),
            )
            conn.commit()
        return report_id

    def find_similar(
        self,
        embedding: list[float],
        top_k: int = 5,
        user_id: str | None = None,
    ) -> list[dict]:
        """
        Return up to top_k past reports most similar to the given embedding,
        ordered closest first. Each result includes a 'similarity' score (0 to 1).
        If user_id is provided, only return reports owned by this user or public/unowned reports.
        If user_id is None, only return unowned/public reports.
        """
        with self._connect() as conn:
            if user_id is not None:
                rows = conn.execute(
                    f"""
                    SELECT id, text, metadata, created_at,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM {self.table_name}
                    WHERE (metadata->>'user_id' = %s OR metadata->>'user_id' IS NULL)
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (embedding, str(user_id), embedding, top_k),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT id, text, metadata, created_at,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM {self.table_name}
                    WHERE metadata->>'user_id' IS NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (embedding, embedding, top_k),
                ).fetchall()
        return [dict(row) for row in rows]

    def delete_report(self, report_id: str) -> None:
        with self._connect() as conn:
            conn.execute(f"DELETE FROM {self.table_name} WHERE id = %s", (report_id,))
            conn.commit()


if __name__ == "__main__":
    # Quick manual check — run: python -m memory.ltm
    from memory.embeddings import embed

    ltm = LongTermMemory()
    ltm.init_schema()
    print("Schema ready.")

    sample_reports = [
        "Report on the best budget laptops for students in 2026.",
        "Report on climate policy changes in the European Union.",
        "Report on the history of the Roman aqueduct system.",
    ]
    for text in sample_reports:
        ltm.store_report(text=text, embedding=embed(text), metadata={"demo": True})

    query = "cheap laptops recommended for college students"
    results = ltm.find_similar(embed(query), top_k=2)
    print(f"\nQuery: '{query}'")
    for r in results:
        print(f"  similarity={r['similarity']:.3f}  text={r['text']}")