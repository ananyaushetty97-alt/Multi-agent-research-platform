import psycopg
from psycopg.rows import dict_row

conn = psycopg.connect('postgresql://postgres:devpassword@localhost:5432/research_platform', row_factory=dict_row)
cur = conn.cursor()

cur.execute("""
    SELECT
        tc.table_name, 
        kcu.column_name, 
        ccu.table_name AS foreign_table_name,
        ccu.column_name AS foreign_column_name,
        tc.constraint_name
    FROM 
        information_schema.table_constraints AS tc 
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
          ON ccu.constraint_name = tc.constraint_name
          AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema='public';
""")
for r in cur.fetchall():
    print(r['table_name'], '.', r['column_name'], '->', r['foreign_table_name'], '.', r['foreign_column_name'], f"({r['constraint_name']})")
