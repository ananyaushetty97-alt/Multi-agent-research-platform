import sys
import json
import uuid
sys.path.insert(0, ".")
import psycopg
from user_auth.config import settings

dsn = settings.postgres_dsn or 'postgresql://postgres:devpassword@localhost:5432/research_platform'
conn = psycopg.connect(dsn)
cur = conn.cursor()

# Ensure compatible columns on public.users
cur.execute("""
    ALTER TABLE public.users ADD COLUMN IF NOT EXISTS username VARCHAR(255);
    ALTER TABLE public.users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'user';
    ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
    ALTER TABLE public.users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255);
""")
# Backfill username and full_name from name/email where null
cur.execute("""
    UPDATE public.users 
    SET username = COALESCE(username, SPLIT_PART(email, '@', 1)),
        full_name = COALESCE(full_name, name),
        role = COALESCE(role, 'user'),
        is_active = COALESCE(is_active, status != 'suspended')
    WHERE username IS NULL OR full_name IS NULL OR role IS NULL;
""")
conn.commit()

print("Checking user_activity_logs count vs activity_logs count...")
cur.execute("SELECT COUNT(*) FROM user_activity_logs")
ual_cnt = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM activity_logs")
al_cnt = cur.fetchone()[0]
print(f"user_activity_logs: {ual_cnt}, activity_logs: {al_cnt}")

# Map user email to user_id from users table
cur.execute("SELECT id, LOWER(email) FROM users")
email_to_uid = {row[1]: str(row[0]) for row in cur.fetchall()}

print(f"Loaded {len(email_to_uid)} user email mappings.")

# Read all rows from user_activity_logs
cur.execute("""
    SELECT id, timestamp, session_id, username, email, action, topic, status, details, client_ip, user_agent
    FROM user_activity_logs
""")
rows = cur.fetchall()
migrated = 0

for r in rows:
    log_id = r[0] or uuid.uuid4()
    ts = r[1]
    session_id = r[2]
    uname = r[3]
    email = (r[4] or "").strip().lower()
    action = r[5] or "user_activity"
    topic = r[6]
    status_val = r[7]
    details = r[8] or {}
    client_ip = r[9]
    uagent = r[10]

    # Map action (e.g. guardrail.block -> guardrail_block)
    event_type = action.replace(".", "_")
    target_uid = email_to_uid.get(email)

    metadata = {
        "legacy_action": action,
        "session_id": session_id,
        "username": uname or (email.split('@')[0] if email else "anonymous"),
        "email": email or "[legacy/unassociated]",
        "topic": topic,
        "status": status_val,
        "migrated_from": "user_activity_logs",
    }
    if isinstance(details, dict):
        metadata.update(details)

    # Insert into activity_logs if not already there
    cur.execute("""
        INSERT INTO public.activity_logs (id, user_id, event_type, metadata, ip_address, user_agent, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING;
    """, (
        log_id,
        target_uid,
        event_type,
        json.dumps(metadata),
        client_ip,
        uagent,
        ts,
    ))
    migrated += 1

conn.commit()

cur.execute("SELECT COUNT(*) FROM activity_logs")
new_al_cnt = cur.fetchone()[0]
print(f"Migrated {migrated} rows. New activity_logs count: {new_al_cnt}")
