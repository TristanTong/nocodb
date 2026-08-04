# -*- coding: utf-8 -*-
import os
import psycopg2

conn = psycopg2.connect(
    host=os.environ.get("MLHR_PG_HOST", "192.168.100.89"),
    port=int(os.environ.get("MLHR_PG_PORT", "5432")),
    user=os.environ.get("MLHR_PG_USER", "postgres"),
    password=os.environ["MLHR_PG_PASSWORD"],
    dbname=os.environ.get("MLHR_PG_DB", "mldata"),
)
cur = conn.cursor()
cur.execute(
    """
    SELECT c.relname AS table_name, a.attname AS column_name, pg_catalog.format_type(a.atttypid, a.atttypmod)
    FROM pg_attribute a
    JOIN pg_class c ON a.attrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'mlhr' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
    ORDER BY c.relname, a.attnum
    """
)
cur_table = None
for t, col, typ in cur.fetchall():
    if t != cur_table:
        print(f"\n== {t} ==")
        cur_table = t
    print(f"  {col}: {typ}")
cur.close()
conn.close()
