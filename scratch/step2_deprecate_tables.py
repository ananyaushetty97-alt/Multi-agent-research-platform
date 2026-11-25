import sys
sys.path.insert(0, ".")
import psycopg
from psycopg.rows import dict_row

conn = psycopg.connect('postgresql://postgres:devpassword@localhost:5432/research_platform', row_factory=dict_row)
cur = conn.cursor()

print("--- 1. Dropping unused tables public.messages and public.conversations ---")
cur.execute("DROP TABLE IF EXISTS public.messages CASCADE;")
cur.execute("DROP TABLE IF EXISTS public.conversations CASCADE;")
conn.commit()
print("Dropped public.messages and public.conversations successfully.")

print("\n--- 2. Updating chat_sessions foreign key to reference public.users(id) ---")
cur.execute("ALTER TABLE public.chat_sessions DROP CONSTRAINT IF EXISTS chat_sessions_user_id_fkey;")
cur.execute("""
    ALTER TABLE public.chat_sessions 
    ADD CONSTRAINT chat_sessions_user_id_fkey 
    FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
""")
conn.commit()
print("Updated chat_sessions_user_id_fkey -> public.users(id) successfully.")

print("\n--- 3. Verifying remaining tables in schema ---")
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    ORDER BY table_name;
""")
tables = [r['table_name'] for r in cur.fetchall()]
print("Current public tables:", tables)
assert 'conversations' not in tables
assert 'messages' not in tables
assert 'chat_sessions' in tables
assert 'chat_messages' in tables

print("\n--- 4. Verifying admin queries run directly against active tables ---")
from user_auth.storage import PostgresUserAuthStorage
from user_auth.chat_storage import PostgresChatReviewStorage

auth_store = PostgresUserAuthStorage()
chat_store = PostgresChatReviewStorage()

stats = auth_store.get_user_summary_stats()
stats["total_conversations"] = chat_store.get_total_conversations_count()
stats["total_messages"] = chat_store.get_total_messages_count()
print("Admin summary stats:", stats)

users = auth_store.list_users(limit=10)
print(f"Listed {len(users)} users:")
for u in users:
    print(f" - {u['email']}: total_conversations={u['total_conversations']}, total_messages={u['total_messages']}")

print("\nSTEP 2 VERIFIED SUCCESSFULLY!")
