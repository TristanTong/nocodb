#!/usr/bin/env python3
"""Fix nc_order uidt for one table on prod Meta (100.97), via 100.89 docker network."""
from __future__ import annotations

import os
import sys
import time

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

JUMP = "192.168.100.89"
JUMP_PWD = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")
PROD = "192.168.100.93"
PROD_PWD = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")

TABLE_ID = "ml7vrxmx5x9y7pu"
VIEW_ID = "vwncjefh9as7wsyr"
BASE_ID = "pys0rzjz5mgwkzy"


def run(c, cmd, timeout=90):
    print(f"\n$ {cmd[:280]}", flush=True)
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip()[:5000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def psql(sql: str) -> str:
    return (
        "docker run --rm --network host -e PGPASSWORD=Pass@w0rd postgres:13 "
        f"psql -h 192.168.100.97 -U postgres -d mlnoco -c {repr(sql)}"
    )


def main():
    j = paramiko.SSHClient()
    j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    j.connect(JUMP, username="root", password=JUMP_PWD, timeout=30)

    p = paramiko.SSHClient()
    p.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    p.connect(PROD, username="root", password=PROD_PWD, timeout=30)

    try:
        run(
            j,
            psql(
                f"SELECT id, title, table_name, base_id, source_id "
                f"FROM nc_models_v2 WHERE id='{TABLE_ID}' OR id='{VIEW_ID}' OR base_id='{BASE_ID}' "
                f"ORDER BY type, id LIMIT 20;"
            ),
        )
        run(
            j,
            psql(
                f"SELECT id, title, column_name, uidt, system, pk "
                f"FROM nc_columns_v2 WHERE fk_model_id='{TABLE_ID}' "
                f"AND (column_name='nc_order' OR uidt='Order') "
                f"ORDER BY column_name;"
            ),
        )
        run(
            j,
            psql(
                f"SELECT id, fk_view_id, fk_column_id, direction "
                f"FROM nc_sort_v2 WHERE fk_view_id='{VIEW_ID}';"
            ),
        )

        # Fix only this table's nc_order
        run(
            j,
            psql(
                f"UPDATE nc_columns_v2 SET uidt='Order', system=true "
                f"WHERE fk_model_id='{TABLE_ID}' AND column_name='nc_order' AND uidt<>'Order' "
                f"RETURNING id, title, column_name, uidt, system;"
            ),
        )
        run(
            j,
            psql(
                f"SELECT id, title, column_name, uidt, system "
                f"FROM nc_columns_v2 WHERE fk_model_id='{TABLE_ID}' AND column_name='nc_order';"
            ),
        )

        # Restart prod API to drop meta cache
        run(p, "cd /opt/mlnocodb && docker compose restart api")
        time.sleep(20)
        run(p, "curl -s -m 10 http://127.0.0.1:6080/api/v1/health; echo")
        run(p, "curl -s -m 10 http://127.0.0.1/api/v1/health; echo")
    finally:
        j.close()
        p.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
