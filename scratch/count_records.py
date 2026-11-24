import os
import sys
sys.path.insert(0, os.path.abspath("."))
import psycopg
from admin_backend.config import settings

def get_all_table_counts():
    dsn = settings.resolve_postgres_dsn()
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name;
            """)
            tables = [r[0] for r in cur.fetchall()]
            print("--- ALL PUBLIC TABLES AND COUNTS ---")
            for t in tables:
                try:
                    cur.execute(f'SELECT COUNT(*) FROM "{t}";')
                    cnt = cur.fetchone()[0]
                    print(f"{t}: {cnt}")
                except Exception as e:
                    conn.rollback()
                    print(f"{t}: error {e}")

if __name__ == "__main__":
    get_all_table_counts()
