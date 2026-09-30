#!/usr/bin/env python3
"""Hide system auto cols in grid views for source bkpov35slyra0jj via Meta PG."""
from __future__ import annotations

import os

import paramiko

HOST93 = "192.168.100.93"
PWD93 = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")
PG_HOST = "192.168.100.97"
PG_USER = "postgres"
PG_PASS = os.environ.get("PG_PASSWORD", "Pass@w0rd")
PG_DB = "mlnoco"
SOURCE = "bkpov35slyra0jj"

REMOTE_PY = f"""
import sys
try:
    import psycopg2
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'psycopg2-binary'])
    import psycopg2

conn = psycopg2.connect(host='{PG_HOST}', user='{PG_USER}', password='{PG_PASS}', dbname='{PG_DB}')
conn.autocommit = True
cur = conn.cursor()

# discover table names
cur.execute(\"\"\"
SELECT tablename FROM pg_tables
WHERE schemaname='public' AND tablename LIKE 'nc_%column%'
ORDER BY 1
\"\"\")
print('tables', cur.fetchall())

# Prefer v2 names; fallback
candidates = [
    ('nc_columns_v2', 'nc_models_v2', 'nc_grid_view_columns_v2', 'nc_views_v2'),
    ('nc_columns', 'nc_models', 'nc_grid_view_columns', 'nc_views'),
]
chosen = None
for cols, models, gvc, views in candidates:
    cur.execute('SELECT to_regclass(%s)', (f'public.{{cols}}',))
    if cur.fetchone()[0]:
        chosen = (cols, models, gvc, views)
        break
print('schema', chosen)
if not chosen:
    raise SystemExit('no meta tables')
COLS, MODELS, GVC, VIEWS = chosen
src = '{SOURCE}'

cur.execute(f'''
SELECT c.id, c.title, c.uidt, m.title
FROM {{COLS}} c
JOIN {{MODELS}} m ON m.id = c.fk_model_id
WHERE m.source_id = %s
  AND c.uidt IN ('CreatedTime','LastModifiedTime','CreatedBy','LastModifiedBy')
ORDER BY m.title, c.uidt
''', (src,))
rows = cur.fetchall()
print('autogen_cols', len(rows))
for r in rows:
    print(r)

cur.execute(f'''
UPDATE {{GVC}} g
SET show = false
FROM {{COLS}} c
JOIN {{MODELS}} m ON m.id = c.fk_model_id
WHERE g.fk_column_id = c.id
  AND m.source_id = %s
  AND c.uidt IN ('CreatedTime','LastModifiedTime','CreatedBy','LastModifiedBy')
  AND COALESCE(g.show, true) = true
''', (src,))
print('updated_rows', cur.rowcount)

cur.execute(f'''
SELECT m.title, v.title, c.title, c.uidt, g.show
FROM {{GVC}} g
JOIN {{COLS}} c ON c.id = g.fk_column_id
JOIN {{MODELS}} m ON m.id = c.fk_model_id
JOIN {{VIEWS}} v ON v.id = g.fk_view_id
WHERE m.source_id = %s
  AND c.uidt IN ('CreatedTime','LastModifiedTime','CreatedBy','LastModifiedBy')
  AND g.show IS TRUE
''', (src,))
left = cur.fetchall()
print('still_shown', len(left))
for r in left:
    print(r)
cur.close(); conn.close()
print('META_OK')
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST93, username="root", password=PWD93, timeout=30)
    try:
        sftp = c.open_sftp()
        with sftp.file("/tmp/hide_autogen_meta.py", "w") as f:
            f.write(REMOTE_PY)
        sftp.close()
        cmds = [
            "python3 /tmp/hide_autogen_meta.py",
            "python /tmp/hide_autogen_meta.py",
            "docker run --rm --network host -v /tmp/hide_autogen_meta.py:/tmp/hide_autogen_meta.py:ro "
            "python:3.11-slim bash -lc 'pip -q install psycopg2-binary && python /tmp/hide_autogen_meta.py'",
        ]
        for cmd in cmds:
            print("TRY", cmd[:100], flush=True)
            _, o, e = c.exec_command(cmd, timeout=300)
            out = o.read().decode("utf-8", "replace")
            err = e.read().decode("utf-8", "replace")
            code = o.channel.recv_exit_status()
            print(out[-4000:], flush=True)
            if err.strip():
                print("ERR", err[-1000:], flush=True)
            if code == 0 and "META_OK" in out:
                return 0
        return 1
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
