#!/usr/bin/env python3
"""Load schema.sql into Postgres"""
# This project was developed with assistance from AI tools.

import psycopg2

CONN_STRING = "postgresql://agent:changeme123@localhost:5432/agentic_orchestrator"

with open("schema.sql", "r") as f:
    schema_sql = f.read()

conn = psycopg2.connect(CONN_STRING)
cur = conn.cursor()

print("Loading schema...")
cur.execute(schema_sql)
conn.commit()

print("✅ Schema loaded successfully")

cur.close()
conn.close()