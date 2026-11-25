import psycopg
from psycopg.rows import dict_row

conn = psycopg.connect('postgresql://postgres:devpassword@localhost:5432/research_platform', row_factory=dict_row)
cur = conn.cursor()

for t in ['user_activity_logs', 'audit_logs', 'reports', 'user_sessions', 'user_sessions_v2', 'chat_sessions']:
    cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='{t}';")
    cols = [r['column_name'] for r in cur.fetchall()]
    print(t, '->', cols)
