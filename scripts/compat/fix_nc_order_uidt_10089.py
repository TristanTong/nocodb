#!/usr/bin/env python3
"""Repair nc_order columns mistyped as Decimal → Order on 100.89, then restart API."""
from __future__ import annotations

import os
import sys
import time

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")


def run(c, cmd, timeout=60):
    print(f"\n$ {cmd[:260]}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip()[:5000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(
            c,
            "docker exec postgres psql -U postgres -d mlnoco -c "
            "\"SELECT uidt, system, count(*) FROM nc_columns_v2 "
            "WHERE column_name='nc_order' GROUP BY uidt, system;\"",
        )

        # Fix mistyped order columns so grid drag-handle enables
        run(
            c,
            "docker exec postgres psql -U postgres -d mlnoco -c "
            "\"UPDATE nc_columns_v2 "
            "SET uidt='Order', system=true "
            "WHERE column_name='nc_order' AND uidt <> 'Order';\"",
        )

        run(
            c,
            "docker exec postgres psql -U postgres -d mlnoco -c "
            "\"SELECT uidt, system, count(*) FROM nc_columns_v2 "
            "WHERE column_name='nc_order' GROUP BY uidt, system;\"",
        )
        run(
            c,
            "docker exec postgres psql -U postgres -d mlnoco -c "
            "\"SELECT id, title, column_name, uidt, system FROM nc_columns_v2 "
            "WHERE id='c3sggsn0zdpmz4y';\"",
        )

        # Restart API to drop in-memory meta cache
        run(c, "cd /opt/mlnocodb && docker compose restart api")
        time.sleep(18)
        run(c, "curl -s -m 10 http://127.0.0.1/api/v1/health; echo")
        run(
            c,
            "curl -s -m 10 -o /dev/null -w 'meta=%{http_code}\\n' "
            "http://127.0.0.1/api/v2/meta/tables/mkrpoejzwnaynqh",
        )
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
