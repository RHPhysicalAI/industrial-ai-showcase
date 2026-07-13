#!/usr/bin/env python3
import psycopg2

CONN_STRING = "postgresql://gridops:u,2:R70VbUU]{r]-PN.qyScg@localhost:5432/gridops"

conn = psycopg2.connect(CONN_STRING)
cur = conn.cursor()

# Check user privileges
cur.execute("""
SELECT
    grantee,
    table_schema,
    privilege_type
FROM information_schema.table_privileges
WHERE grantee = 'gridops'
LIMIT 10;
""")
print("User privileges:")
for row in cur.fetchall():
    print(f"  {row}")

# Check existing tables
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
print("\nExisting tables in public schema:")
for row in cur.fetchall():
    print(f"  {row[0]}")

cur.close()
conn.close()
