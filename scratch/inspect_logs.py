import sys
sys.path.insert(0, ".")
import psycopg
from user_auth.config import settings

dsn = settings.postgres_dsn or 'postgresql://postgres:devpassword@localhost:5432/research_platform'
conn = psycopg.connect(dsn)
cur = conn.cursor()

print("--- user_activity_logs columns ---")
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'user_activity_logs'")
for col in cur.fetchall():
    print(col)

print("--- activity_logs columns ---")
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'activity_logs'")
for col in cur.fetchall():
    print(col)

print("--- sample user_activity_logs ---")
cur.execute("SELECT * FROM user_activity_logs LIMIT 3")
for row in cur.fetchall():
    print(row)
