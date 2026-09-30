#!/usr/bin/env python3
"""Add nc_order to factsxshippingcomm (DWS) + meta on 100.97 for drag reorder."""
from __future__ import annotations

import os
import secrets
import string
import time

import paramiko

JUMP = "192.168.100.89"
JUMP_PWD = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")
PROD = "192.168.100.93"
PROD_PWD = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")

TABLE_ID = "ml7vrxmx5x9y7pu"
VIEW_ID = "vwncjefh9as7wsyr"
BASE_ID = "pys0rzjz5mgwkzy"
SOURCE_ID = "bo7uyto2o0xk4ti"
WS_ID = "w30hbjoc"

# Integration midp (source overrides DB to metabase_dws)
DWS_HOSTS = [
    ("192.168.100.88", "sa", "G2d#S8b@K5zQ"),
    ("192.168.100.99", "sa", "PassW0rd@321"),
]


def nid(prefix: str, n: int = 14) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return prefix + "".join(secrets.choice(alphabet) for _ in range(n))


def run(c, cmd, timeout=120):
    print(f"\n$ {cmd[:280]}", flush=True)
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    print(out.rstrip()[:7000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def find_dws(j):
    for host, user, pw in DWS_HOSTS:
        cmd = (
            "docker run --rm --network host "
            f"-e PGPASSWORD='{pw}' postgres:13 "
            f"psql -h {host} -U {user} -d metabase_dws -tAc "
            "\"SELECT current_database()||'|'||count(*) FROM information_schema.columns "
            "WHERE table_schema='dbo' AND table_name='factsxshippingcomm';\""
        )
        code, out = run(j, cmd, timeout=30)
        if code == 0 and "metabase_dws|" in out and "error" not in out.lower():
            return host, user, pw
    raise RuntimeError("DWS host not reachable")


def main():
    j = paramiko.SSHClient()
    j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    j.connect(JUMP, username="root", password=JUMP_PWD, timeout=30)
    p = paramiko.SSHClient()
    p.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    p.connect(PROD, username="root", password=PROD_PWD, timeout=30)

    col_id = nid("c")
    gv_id = nid("nc")

    try:
        host, user, pw = find_dws(j)
        print(f"Using DWS {user}@{host}/metabase_dws", flush=True)

        # Physical DDL + backfill
        dws_sql = f"""
SELECT column_name FROM information_schema.columns
WHERE table_schema='dbo' AND table_name='factsxshippingcomm' AND column_name='nc_order';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='dbo' AND table_name='factsxshippingcomm' AND column_name='nc_order'
  ) THEN
    ALTER TABLE dbo.factsxshippingcomm ADD COLUMN nc_order numeric;
  END IF;
END $$;

UPDATE dbo.factsxshippingcomm
SET nc_order = id
WHERE nc_order IS NULL;

CREATE INDEX IF NOT EXISTS factsxshippingcomm_order_idx ON dbo.factsxshippingcomm (nc_order);

SELECT count(*) AS rows, min(nc_order) AS min_o, max(nc_order) AS max_o
FROM dbo.factsxshippingcomm;
"""
        sftp = j.open_sftp()
        with sftp.file("/tmp/dws_add_order.sql", "w") as f:
            f.write(dws_sql)
        sftp.close()
        code, _ = run(
            j,
            f"docker run --rm --network host -e PGPASSWORD='{pw}' "
            f"-v /tmp/dws_add_order.sql:/tmp/s.sql:ro postgres:13 "
            f"psql -h {host} -U {user} -d metabase_dws -v ON_ERROR_STOP=1 -f /tmp/s.sql",
        )
        if code != 0:
            return 1

        # Meta insert (only if missing)
        meta_sql = f"""
SELECT id, uidt, system FROM nc_columns_v2
WHERE fk_model_id='{TABLE_ID}' AND column_name='nc_order';

INSERT INTO nc_columns_v2 (
  id, base_id, source_id, fk_model_id, title, column_name, uidt, dt, dtx,
  system, pk, pv, rqd, un, ai, au, \"order\", meta, created_at, updated_at, fk_workspace_id
)
SELECT
  '{col_id}', '{BASE_ID}', '{SOURCE_ID}', '{TABLE_ID}', 'nc_order', 'nc_order',
  'Order', 'numeric', 'specificType',
  true, false, null, false, false, false, false, 6, '{{}}'::json,
  now(), now(), '{WS_ID}'
WHERE NOT EXISTS (
  SELECT 1 FROM nc_columns_v2 WHERE fk_model_id='{TABLE_ID}' AND column_name='nc_order'
);

UPDATE nc_columns_v2
SET uidt='Order', system=true, dt='numeric', dtx='specificType'
WHERE fk_model_id='{TABLE_ID}' AND column_name='nc_order';

SELECT id, title, column_name, uidt, system, dt
FROM nc_columns_v2
WHERE fk_model_id='{TABLE_ID}' AND column_name='nc_order';

-- attach to grid view as hidden system field if missing
INSERT INTO nc_grid_view_columns_v2 (
  id, fk_view_id, fk_column_id, source_id, base_id, width, show, \"order\",
  created_at, updated_at, fk_workspace_id
)
SELECT
  '{gv_id}', '{VIEW_ID}', c.id, '{SOURCE_ID}', '{BASE_ID}', '200px', false, 0,
  now(), now(), '{WS_ID}'
FROM nc_columns_v2 c
WHERE c.fk_model_id='{TABLE_ID}' AND c.column_name='nc_order'
  AND NOT EXISTS (
    SELECT 1 FROM nc_grid_view_columns_v2 g
    WHERE g.fk_view_id='{VIEW_ID}' AND g.fk_column_id=c.id
  );

SELECT g.id, g.fk_view_id, g.fk_column_id, g.show, g.\"order\"
FROM nc_grid_view_columns_v2 g
JOIN nc_columns_v2 c ON c.id=g.fk_column_id
WHERE g.fk_view_id='{VIEW_ID}' AND c.column_name='nc_order';
"""
        sftp = j.open_sftp()
        with sftp.file("/tmp/meta_add_order.sql", "w") as f:
            f.write(meta_sql)
        sftp.close()
        code, _ = run(
            j,
            "docker run --rm --network host -e PGPASSWORD=Pass@w0rd "
            "-v /tmp/meta_add_order.sql:/tmp/s.sql:ro postgres:13 "
            "psql -h 192.168.100.97 -U postgres -d mlnoco -v ON_ERROR_STOP=1 -f /tmp/s.sql",
        )
        if code != 0:
            return 1

        run(p, "cd /opt/mlnocodb && docker compose restart api")
        time.sleep(20)
        run(p, "curl -s -m 10 http://127.0.0.1/api/v1/health; echo")
        print(
            f"\nDone. Refresh view {VIEW_ID} on table {TABLE_ID}. "
            "Hover row index to drag. Ensure view has no sorts.",
            flush=True,
        )
    finally:
        j.close()
        p.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
