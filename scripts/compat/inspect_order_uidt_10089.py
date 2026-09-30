#!/usr/bin/env python3
"""Inspect nc_order columns and fix uidt Decimal -> Order for target table."""
from __future__ import annotations

import os
import sys

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")


def run(c, sql):
    cmd = f"docker exec postgres psql -U postgres -d mlnoco -c {repr(sql)}"
    print(f"\nSQL> {sql}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=40, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    print(out.rstrip()[:5000], flush=True)
    if err.strip():
        print("ERR:", err[:1000], flush=True)
    return out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(
            c,
            "SELECT id, fk_model_id, title, column_name, uidt, system, pk "
            "FROM nc_columns_v2 WHERE column_name='nc_order' OR uidt='Order' "
            "ORDER BY fk_model_id LIMIT 50;",
        )
        run(
            c,
            "SELECT id, fk_view_id, fk_column_id, direction "
            "FROM nc_sort_v2 WHERE fk_view_id='vw8ygjt8vwuh9ncb';",
        )
        run(
            c,
            "SELECT id, title, type, base_id, source_id "
            "FROM nc_models_v2 WHERE id='mkrpoejzwnaynqh';",
        )
        # Compare with a known good Order column if any
        run(
            c,
            "SELECT uidt, count(*) FROM nc_columns_v2 "
            "WHERE column_name='nc_order' GROUP BY uidt;",
        )
        # Sample a correct Order column meta
        run(
            c,
            "SELECT id, title, column_name, uidt, system, meta, dt, dtx, cdf "
            "FROM nc_columns_v2 WHERE uidt='Order' LIMIT 3;",
        )
        run(
            c,
            "SELECT id, title, column_name, uidt, system, meta, dt, dtx, cdf "
            "FROM nc_columns_v2 WHERE id='c3sggsn0zdpmz4y';",
        )
    finally:
        c.close()


if __name__ == "__main__":
    main()
