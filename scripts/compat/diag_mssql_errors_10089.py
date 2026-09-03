#!/usr/bin/env python3
"""Diagnose MSSQL source errors on 100.89 for base pw4yksn9i7x1fx4."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")
BASE = "pw4yksn9i7x1fx4"
TABLE = "mfovsj7l4h4g32p"
VIEW = "vwb8kfp4g9kdkb11"


def run(c, cmd, timeout=60):
    print(f"\n$ {cmd[:280]}", flush=True)
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    print(out.rstrip()[:6000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(
            c,
            "docker exec mlnocodb-api sh -c "
            "'echo size=$(wc -c </usr/src/app/docker/main.js); "
            "echo sha=$(sha256sum /usr/src/app/docker/main.js|cut -c1-16); "
            "echo MssqlClient=$(grep -o MssqlClient /usr/src/app/docker/main.js|wc -l); "
            "echo mssqlBranch=$(grep -o \"\\\"mssql\\\"===e.client\" /usr/src/app/docker/main.js|wc -l); "
            "node -e \"try{require(\\\"mssql\\\");console.log(\\\"mssql_pkg=ok\\\")}catch(e){console.log(\\\"mssql_missing\\\")}\"'",
        )
        run(
            c,
            "wc -c /opt/mlnocodb/build/docker/main.js; "
            "grep -c MssqlClient /opt/mlnocodb/build/docker/main.js; "
            "grep -c '\"mssql\"===e.client' /opt/mlnocodb/build/docker/main.js",
        )
        # Meta: base/sources/table
        run(
            c,
            "docker exec postgres psql -U postgres -d mlnoco -c "
            f"\"SELECT id,title FROM nc_bases_v2 WHERE id='{BASE}';\"",
        )
        run(
            c,
            "docker exec postgres psql -U postgres -d mlnoco -c "
            f"\"SELECT id,alias,type,is_schema_readonly,is_data_readonly,fk_integration_id,"
            f"left(config::text,120) cfg FROM nc_sources_v2 WHERE base_id='{BASE}';\"",
        )
        run(
            c,
            "docker exec postgres psql -U postgres -d mlnoco -c "
            f"\"SELECT id,title,table_name,type,source_id FROM nc_models_v2 WHERE id='{TABLE}' OR base_id='{BASE}' ORDER BY type,id LIMIT 30;\"",
        )
        run(
            c,
            "docker logs --tail 80 mlnocodb-api 2>&1 | tr -cd '\\11\\12\\15\\40-\\176\\n' | tail -80",
        )
        # Trigger APIs from inside host with a fresh signin if we can find password
        # List users
        run(
            c,
            "docker exec postgres psql -U postgres -d mlnoco -c "
            "\"SELECT id,email FROM nc_users_v2 ORDER BY created_at NULLS LAST LIMIT 10;\"",
        )
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
