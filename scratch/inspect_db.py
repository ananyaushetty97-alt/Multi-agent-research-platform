import sys
sys.path.insert(0, ".")
import psycopg
from user_auth.config import settings

dsn = settings.postgres_dsn or 'postgresql://postgres:devpassword@localhost:5432/research_platform'
conn = psycopg.connect(dsn)
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
tables = [row[0] for row in cur.fetchall()]
for tbl in tables:
    try:
        cur.execute(f'SELECT COUNT(*) FROM "{tbl}"')
        cnt = cur.fetchone()[0]
        print(f'{tbl}: {cnt} rows')
    except Exception as e:
        print(f'{tbl}: error {e}')
