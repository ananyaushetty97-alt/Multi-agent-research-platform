import psycopg
from psycopg.rows import dict_row

conn = psycopg.connect('postgresql://postgres:devpassword@localhost:5432/research_platform', row_factory=dict_row)
cur = conn.cursor()

tables = [
    'users',
    'admin_users',
    'activity_logs',
    'user_activity_logs',
    'audit_logs',
    'user_sessions',
    'user_sessions_v2',
    'otp_verifications',
    'password_resets',
    'chat_sessions',
    'chat_messages',
    'reports',
]

def get_counts():
    counts = {}
    for t in tables:
        cur.execute(f"SELECT COUNT(*) as cnt FROM public.{t};")
        counts[t] = cur.fetchone()['cnt']
    return counts

counts_before = get_counts()

# Find test users
cur.execute("""
    SELECT id, email, name, auth_provider FROM public.users
    WHERE email LIKE '%@example.com'
       OR email LIKE 'test%'
       OR email LIKE 'live_test%'
       OR email LIKE 'reviewer_%'
       OR email LIKE 'diag%'
       OR email IN ('ram@gmail.com', 'shyam@gmail.com', 'sudeep@gmail.com');
""")
test_users = cur.fetchall()
test_user_ids = [str(u['id']) for u in test_users]
test_emails = [u['email'] for u in test_users]
test_usernames = [u['email'].split('@')[0] for u in test_users]

print(f"Found {len(test_users)} test users to delete:")
for u in test_users[:10]:
    print(f" - {u['email']} ({u['name']})")
if len(test_users) > 10:
    print(f" ... and {len(test_users) - 10} more.")

if test_user_ids:
    # 1. Activity logs
    cur.execute("DELETE FROM public.activity_logs WHERE user_id = ANY(%s::uuid[]) OR metadata->>'email' = ANY(%s);", (test_user_ids, test_emails))
    
    # 2. Legacy user activity logs
    cur.execute("DELETE FROM public.user_activity_logs WHERE email = ANY(%s) OR username = ANY(%s);", (test_emails, test_usernames))
    
    # 3. Audit logs
    cur.execute("DELETE FROM public.audit_logs WHERE actor_username = ANY(%s) OR actor_username = ANY(%s);", (test_emails, test_usernames))
    
    # 4. User sessions
    cur.execute("DELETE FROM public.user_sessions WHERE user_id = ANY(%s::uuid[]);", (test_user_ids,))
    cur.execute("DELETE FROM public.user_sessions_v2 WHERE user_id = ANY(%s::uuid[]);", (test_user_ids,))
    
    # 5. OTP and password resets
    cur.execute("DELETE FROM public.otp_verifications WHERE user_id = ANY(%s::uuid[]) OR email = ANY(%s);", (test_user_ids, test_emails))
    cur.execute("DELETE FROM public.password_resets WHERE user_id = ANY(%s::uuid[]);", (test_user_ids,))

    # 6. Chat messages & sessions
    cur.execute("DELETE FROM public.chat_messages WHERE session_id IN (SELECT id FROM public.chat_sessions WHERE user_id = ANY(%s::uuid[]));", (test_user_ids,))
    cur.execute("DELETE FROM public.chat_sessions WHERE user_id = ANY(%s::uuid[]);", (test_user_ids,))

    # 8. Reports (if metadata has user_id or email)
    for uid in test_user_ids:
        cur.execute("DELETE FROM public.reports WHERE metadata->>'user_id' = %s;", (uid,))

    # 9. Finally delete test users
    cur.execute("DELETE FROM public.users WHERE id = ANY(%s::uuid[]);", (test_user_ids,))
    conn.commit()

counts_after = get_counts()

print("\n================== ROW COUNTS BEFORE AND AFTER CLEANUP ==================")
print(f"{'Table Name':<25} | {'Before':<10} | {'After':<10} | {'Diff':<10}")
print("-" * 65)
for t in tables:
    before = counts_before[t]
    after = counts_after[t]
    diff = after - before
    print(f"{t:<25} | {before:<10} | {after:<10} | {diff:<10}")

print("\n--- REMAINING USERS IN public.users ---")
cur.execute("SELECT id, email, name, role, auth_provider FROM public.users;")
for u in cur.fetchall():
    print(dict(u))

print("\n--- ADMIN ACCOUNTS IN public.admin_users (PRESERVED) ---")
cur.execute("SELECT id, username, email, role, is_active FROM public.admin_users;")
for a in cur.fetchall():
    print(dict(a))
