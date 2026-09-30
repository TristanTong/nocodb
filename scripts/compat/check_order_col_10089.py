#!/usr/bin/env python3
"""Check whether table mkrpoejzwnaynqh has nc_order / Order column on 100.89 meta DB."""
from __future__ import annotations

import os
import sys

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")

SQL = r"""
SELECT id, title, table_name, base_id, type FROM nc_models_v2 WHERE id='mkrpoejzwnaynqh' OR id='vw8ygjt8vwuh9ncb' OR base_id='pndb7r4p2gozzzx' LIMIT 20;
SELECT id, title, column_name, uidt, system, pk, "order" FROM nc_columns_v2 WHERE fk_model_id='mkrpoejzwnaynqh' ORDER BY "order";
SELECT id, title, type, show_system_fields, lock_type FROM nc_models_v2 WHERE id='vw8ygjt8vwuh9ncb';
SELECT id, title, type FROM nc_models_v2 WHERE fk_model_id='mkrpoejzwnaynqh' OR id='vw8ygjt8vwuh9ncb';
"""


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        # try via docker postgres
        cmd = (
            "docker exec postgres psql -U postgres -d mlnoco -c "
            "\"SELECT id, title, table_name FROM nc_models_v2 WHERE id='mkrpoejzwnaynqh';\" "
            "&& docker exec postgres psql -U postgres -d mlnoco -c "
            "\"SELECT id, title, column_name, uidt, system, pk FROM nc_columns_v2 WHERE fk_model_id='mkrpoejzwnaynqh' ORDER BY \\\"order\\\";\" "
            "&& docker exec postgres psql -U postgres -d mlnoco -c "
            "\"SELECT id, title, type, show_system_fields FROM nc_models_v2 WHERE id='vw8ygjt8vwuh9ncb';\" "
            "&& docker exec postgres psql -U postgres -d mlnoco -c "
            "\"SELECT id, fk_model_id, title, type FROM nc_models_v2 WHERE fk_view_id='vw8ygjt8vwuh9ncb' OR id='vw8ygjt8vwuh9ncb' OR parent_id='mkrpoejzwnaynqh' LIMIT 30;\""
        )
        print(f"$ {cmd[:200]}...", flush=True)
        _, o, e = c.exec_command(cmd, timeout=60, get_pty=True)
        out = o.read().decode("utf-8", "replace")
        err = e.read().decode("utf-8", "replace")
        print(out[:8000], flush=True)
        if err.strip():
            print("ERR:", err[:2000], flush=True)

        # also list view sorts for this view
        cmd2 = (
            "docker exec postgres psql -U postgres -d mlnoco -c "
            "\"\\dt *sort*\" ; "
            "docker exec postgres psql -U postgres -d mlnoco -c "
            "\"SELECT table_name FROM information_schema.tables WHERE table_name ILIKE '%sort%' OR table_name ILIKE '%view%';\""
        )
        _, o2, _ = c.exec_command(cmd2, timeout=40, get_pty=True)
        print(o2.read().decode("utf-8", "replace")[:4000], flush=True)
    finally:
        c.close()


if __name__ == "__main__":
    main()
