#!/usr/bin/env python3
"""Extra version / meta probes for 89 vs 93."""
from __future__ import annotations

import os
import sys

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def ssh(host, pwd):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username="root", password=pwd, timeout=30)
    return c


def run(c, cmd, timeout=40):
    print(f"\n[{c.get_transport().getpeername()[0]}] $ {cmd[:220]}", flush=True)
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    print(o.read().decode("utf-8", "replace").rstrip()[:4000], flush=True)


def main():
    c89 = ssh("192.168.100.89", os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd"))
    c93 = ssh("192.168.100.93", os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025"))
    try:
        for c in (c89, c93):
            run(c, "curl -s -m 8 http://127.0.0.1:6080/api/v1/version; echo")
            run(c, "curl -s -m 8 http://127.0.0.1:6080/api/v1/db/meta/nocodb/info; echo")
            run(
                c,
                "docker exec mlnocodb-api sh -c "
                "'echo size=$(wc -c </usr/src/app/docker/main.js); "
                "echo sha=$(sha256sum /usr/src/app/docker/main.js|cut -c1-16); "
                "echo mssqlClient=$(grep -o MssqlClient /usr/src/app/docker/main.js|wc -l); "
                "echo mssqlBranch=$(grep -o \"\\\"mssql\\\"===e.client\" /usr/src/app/docker/main.js|wc -l); "
                "node -e \"try{require(\\\"mssql\\\");console.log(\\\"mssql_pkg=ok\\\")}catch(e){console.log(\\\"mssql_pkg=missing\\\")}\"'",
            )
            run(
                c,
                "docker images mlnocodb --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedSince}} {{.Size}}'",
            )

        run(
            c89,
            "docker exec postgres psql -U postgres -d mlnoco -tAc "
            "\"SELECT count(*) FROM nc_models_v2 WHERE type='table'; "
            "SELECT count(*) FROM nc_bases_v2;\"",
        )
        # prod meta on 100.97
        run(
            c93,
            "PGPASSWORD='Pass@w0rd' psql -h 192.168.100.97 -U postgres -d mlnoco -c "
            "\"SELECT uidt, count(*) FROM nc_columns_v2 WHERE column_name='nc_order' GROUP BY uidt;\"",
        )
        run(
            c93,
            "PGPASSWORD='Pass@w0rd' psql -h 192.168.100.97 -U postgres -d mlnoco -tAc "
            "\"SELECT count(*) FROM nc_models_v2 WHERE type='table'; "
            "SELECT count(*) FROM nc_bases_v2;\"",
        )
        run(
            c93,
            "cat /opt/mlnocodb/docker-compose.yml",
        )
        run(
            c89,
            "cat /opt/mlnocodb/docker-compose.yml",
        )
    finally:
        c89.close()
        c93.close()


if __name__ == "__main__":
    main()
