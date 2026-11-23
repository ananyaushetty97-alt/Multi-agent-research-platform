import sys
sys.path.insert(0, ".")
import psycopg
from user_auth.config import settings

dsn = settings.postgres_dsn or 'postgresql://postgres:devpassword@localhost:5432/research_platform'
conn = psycopg.connect(dsn)
cur = conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'app_users'")
for col in cur.fetchall():
    print(col)
