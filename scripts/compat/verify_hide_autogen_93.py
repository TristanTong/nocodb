#!/usr/bin/env python3
"""Verify show=false for specific grid view column ids after Meta hide."""
from __future__ import annotations

import os

import paramiko

HOST93 = "192.168.100.93"
PWD93 = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")
PG_PASS = os.environ.get("PG_PASSWORD", "Pass@w0rd")

# from fix_autogen was_shown
VCIDS = [
    "nc76amc4r2yow8be",
    "nch4fjhybsnrg0sh",
    "ncct5szyj56gjpiw",
    "ncl653kww5j2pgha",
    "ncln4fv5lwxh65m9",
    "ncz6142f0bi4h7ro",
    "ncnz2y8tvat9ldxf",
    "nckhuw77kmz57n6v",
    "nc9vp82imenj6h1g",
    "ncoojh5b10itszz7",
    "ncahhglqk9x39iv1",
]

REMOTE_PY = f"""
import sys, subprocess
try:
    import psycopg2
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'psycopg2-binary'])
    import psycopg2
conn = psycopg2.connect(host='192.168.100.97', user='postgres', password='{PG_PASS}', dbname='mlnoco')
cur = conn.cursor()
ids = {VCIDS!r}
cur.execute(
    'SELECT id, show, fk_column_id FROM nc_grid_view_columns_v2 WHERE id = ANY(%s)',
    (ids,),
)
rows = cur.fetchall()
print('found', len(rows))
for r in rows:
    print(r)
shown = [r for r in rows if r[1]]
print('shown_true', len(shown))
# also count all autogen shown for source
cur.execute('''
SELECT count(*) FROM nc_grid_view_columns_v2 g
JOIN nc_columns_v2 c ON c.id = g.fk_column_id
JOIN nc_models_v2 m ON m.id = c.fk_model_id
WHERE m.source_id = 'bkpov35slyra0jj'
  AND c.uidt IN ('CreatedTime','LastModifiedTime','CreatedBy','LastModifiedBy')
  AND g.show IS TRUE
''')
print('source_autogen_shown', cur.fetchone()[0])
cur.close(); conn.close()
print('VERIFY_OK')
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST93, username="root", password=PWD93, timeout=30)
    try:
        sftp = c.open_sftp()
        with sftp.file("/tmp/verify_hide.py", "w") as f:
            f.write(REMOTE_PY)
        sftp.close()
        cmd = (
            "docker run --rm --network host "
            "-v /tmp/verify_hide.py:/tmp/verify_hide.py:ro "
            "python:3.11-slim bash -lc "
            "'pip -q install psycopg2-binary && python /tmp/verify_hide.py'"
        )
        _, o, e = c.exec_command(cmd, timeout=180)
        print(o.read().decode("utf-8", "replace"), flush=True)
        err = e.read().decode("utf-8", "replace")
        if err.strip():
            print("ERR", err[-400:], flush=True)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
