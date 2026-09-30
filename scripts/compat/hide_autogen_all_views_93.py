#!/usr/bin/env python3
"""Hide system auto cols in ALL view-column tables for source bkpov35slyra0jj."""
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
import sys, subprocess
try:
    import psycopg2
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'psycopg2-binary'])
    import psycopg2

conn = psycopg2.connect(host='{PG_HOST}', user='{PG_USER}', password='{PG_PASS}', dbname='{PG_DB}')
conn.autocommit = True
cur = conn.cursor()
src = '{SOURCE}'
tables = [
    'nc_grid_view_columns_v2',
    'nc_form_view_columns_v2',
    'nc_gallery_view_columns_v2',
    'nc_kanban_view_columns_v2',
    'nc_list_view_columns_v2',
    'nc_calendar_view_columns_v2',
    'nc_map_view_columns_v2',
]
for t in tables:
    cur.execute('SELECT to_regclass(%s)', (f'public.{{t}}',))
    if not cur.fetchone()[0]:
        print('skip', t)
        continue
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name='show'",
        (t,),
    )
    if not cur.fetchone():
        print('no_show', t)
        continue
    cur.execute(f'''
UPDATE {{t}} g SET show = false
FROM nc_columns_v2 c
JOIN nc_models_v2 m ON m.id = c.fk_model_id
WHERE g.fk_column_id = c.id
  AND m.source_id = %s
  AND c.uidt IN ('CreatedTime','LastModifiedTime','CreatedBy','LastModifiedBy')
  AND COALESCE(g.show, true) = true
''', (src,))
    print(t, 'updated', cur.rowcount)

# remaining shown in grid
cur.execute('''
SELECT m.title, v.title, c.title, c.uidt, g.show
FROM nc_grid_view_columns_v2 g
JOIN nc_columns_v2 c ON c.id = g.fk_column_id
JOIN nc_models_v2 m ON m.id = c.fk_model_id
JOIN nc_views_v2 v ON v.id = g.fk_view_id
WHERE m.source_id = %s
  AND c.uidt IN ('CreatedTime','LastModifiedTime','CreatedBy','LastModifiedBy')
  AND g.show IS TRUE
''', (src,))
left = cur.fetchall()
print('grid_still_shown', len(left))
for r in left:
    print(r)
cur.close(); conn.close()
print('ALL_VIEWS_OK')
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST93, username="root", password=PWD93, timeout=30)
    try:
        sftp = c.open_sftp()
        with sftp.file("/tmp/hide_all_views.py", "w") as f:
            f.write(REMOTE_PY)
        sftp.close()
        cmd = (
            "docker run --rm --network host "
            "-v /tmp/hide_all_views.py:/tmp/hide_all_views.py:ro "
            "python:3.11-slim bash -lc "
            "'pip -q install psycopg2-binary && python /tmp/hide_all_views.py'"
        )
        _, o, e = c.exec_command(cmd, timeout=300)
        out = o.read().decode("utf-8", "replace")
        err = e.read().decode("utf-8", "replace")
        print(out, flush=True)
        if err.strip():
            print("ERR", err[-600:], flush=True)
        _, o2, _ = c.exec_command(
            "curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/v1/health",
            timeout=20,
        )
        print("health", o2.read().decode(), flush=True)
        return 0 if "ALL_VIEWS_OK" in out else 1
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
