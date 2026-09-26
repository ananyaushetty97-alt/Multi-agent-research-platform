"""
Long-term memory (LTM): stores finished reports with their embeddings in
Postgres (pgvector extension), and retrieves similar past reports later.
"""

import json
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
    def __init__(self, dsn: str | None = None):
        self._dsn = dsn or settings.postgres_dsn

    def _connect(self) -> psycopg.Connection:
        conn = psycopg.connect(self._dsn, row_factory=dict_row)
        register_vector(conn)
        return conn

    def init_schema(self) -> None:
        """Run once (or every startup — it's idempotent) to ensure the table exists."""
        with self._connect() as conn:
            conn.execute(CREATE_TABLE_SQL)
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
                """
                INSERT INTO reports (id, text, embedding, metadata, created_at)
                VALUES (%s, %s, %s::vector, %s, %s)
                """,
                (report_id, text, embedding, json.dumps(metadata), datetime.now(timezone.utc)),
            )
            conn.commit()
        return report_id

    def find_similar(self, embedding: list[float], top_k: int = 5) -> list[dict]:
        """
        Return up to top_k past reports most similar to the given embedding,
        ordered closest first. Each result includes a 'similarity' score (0 to 1).
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, text, metadata, created_at,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM reports
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (embedding, embedding, top_k),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_report(self, report_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM reports WHERE id = %s", (report_id,))
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
