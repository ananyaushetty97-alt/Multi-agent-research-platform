import psycopg

conn = psycopg.connect('postgresql://postgres:devpassword@localhost:5432/research_platform')
cur = conn.cursor()
cur.execute("""
    INSERT INTO public.users (id, name, email, role, auth_provider, email_verified, status)
    VALUES ('be7bb556-cc84-4d2d-b6e9-792bc0bc9881', 'Guest User', 'guest@platform.ai', 'user', 'guest', FALSE, 'active')
    ON CONFLICT (id) DO UPDATE SET name = 'Guest User', email = 'guest@platform.ai';
""")
conn.commit()
print("Guest user created in public.users successfully!")
