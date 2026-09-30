#!/usr/bin/env python3
"""List columns for factsxshippingcomm and create/fix nc_order if missing."""
from __future__ import annotations

import os
import time

import paramiko

JUMP = "192.168.100.89"
JUMP_PWD = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")
PROD = "192.168.100.93"
PROD_PWD = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")
TABLE_ID = "ml7vrxmx5x9y7pu"


def run(c, cmd, timeout=120):
    print(f"\n$ {cmd[:260]}", flush=True)
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    print(out.rstrip()[:7000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def psql(sql: str) -> str:
    # write sql to file on remote to avoid quoting hell
    return sql


def main():
    j = paramiko.SSHClient()
    j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    j.connect(JUMP, username="root", password=JUMP_PWD, timeout=30)

    p = paramiko.SSHClient()
    p.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    p.connect(PROD, username="root", password=PROD_PWD, timeout=30)

    try:
        sftp = j.open_sftp()
        sql_path = "/tmp/fix_nc_order_one.sql"
        sql = f"""
-- inspect
SELECT id, title, column_name, uidt, system, pk, dt
FROM nc_columns_v2
WHERE fk_model_id = '{TABLE_ID}'
ORDER BY id;

SELECT COUNT(*) AS col_count FROM nc_columns_v2 WHERE fk_model_id = '{TABLE_ID}';

-- if nc_order exists as wrong uidt, fix it
UPDATE nc_columns_v2
SET uidt = 'Order', system = true
WHERE fk_model_id = '{TABLE_ID}'
  AND column_name = 'nc_order'
  AND uidt IS DISTINCT FROM 'Order'
RETURNING id, title, column_name, uidt, system;

-- show result
SELECT id, title, column_name, uidt, system
FROM nc_columns_v2
WHERE fk_model_id = '{TABLE_ID}' AND column_name = 'nc_order';
"""
        with sftp.file(sql_path, "w") as f:
            f.write(sql)
        sftp.close()

        run(
            j,
            "docker run --rm --network host -e PGPASSWORD=Pass@w0rd "
            f"-v {sql_path}:/tmp/fix.sql:ro postgres:13 "
            "psql -h 192.168.100.97 -U postgres -d mlnoco -f /tmp/fix.sql",
        )

        # Also check physical column on business source if needed.
        # Source bo7uyto2o0xk4ti — likely external PG. Get connection from nc_sources_v2.
        run(
            j,
            "docker run --rm --network host -e PGPASSWORD=Pass@w0rd postgres:13 "
            "psql -h 192.168.100.97 -U postgres -d mlnoco -c "
            "\"SELECT id, alias, type, LEFT(config::text,200) AS config_head "
            "FROM nc_sources_v2 WHERE id='bo7uyto2o0xk4ti';\"",
        )
    finally:
        j.close()
        p.close()


if __name__ == "__main__":
    main()
