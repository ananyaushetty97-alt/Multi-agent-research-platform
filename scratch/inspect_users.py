import os, sys
sys.path.insert(0, os.path.abspath("."))
import psycopg
from admin_backend.config import settings

dsn = settings.resolve_postgres_dsn()
with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        print("ADMIN USERS:")
        cur.execute("SELECT id, username, email, role, is_active FROM admin_users;")
        for r in cur.fetchall():
            print(r)
        
        print("\nUSERS (sample usernames and emails):")
        cur.execute("SELECT id, name, email, auth_provider, email_verified, status FROM users LIMIT 10;")
        for r in cur.fetchall():
            print(r)
