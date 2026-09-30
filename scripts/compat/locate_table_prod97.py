#!/usr/bin/env python3
"""Locate model ml7vrxmx5x9y7pu / view vwncjefh9as7wsyr on prod Meta 97."""
from __future__ import annotations

import os
import paramiko

JUMP = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")


def run(c, sql):
    cmd = (
        "docker run --rm --network host -e PGPASSWORD=Pass@w0rd postgres:13 "
        f"psql -h 192.168.100.97 -U postgres -d mlnoco -c {repr(sql)}"
    )
    print(f"\nSQL> {sql}", flush=True)
    _, o, _ = c.exec_command(cmd, timeout=90, get_pty=True)
    print(o.read().decode("utf-8", "replace").rstrip()[:6000], flush=True)


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(JUMP, username="root", password=PWD, timeout=30)
    try:
        for sql in [
            "SELECT id, title, table_name, type, base_id, source_id, mm, meta "
            "FROM nc_models_v2 WHERE id IN ('ml7vrxmx5x9y7pu','vwncjefh9as7wsyr','pys0rzjz5mgwkzy','w30hbjoc');",
            "SELECT id, title, type, base_id, source_id FROM nc_models_v2 WHERE id LIKE 'ml7vrx%' OR title ILIKE '%发货%' LIMIT 30;",
            "SELECT id, fk_model_id, title, type FROM nc_views_v2 WHERE id='vwncjefh9as7wsyr' OR fk_model_id='ml7vrxmx5x9y7pu';",
            "SELECT column_name, count(*) FROM information_schema.columns WHERE table_name='nc_views_v2' GROUP BY 1 ORDER BY 1;",
            "SELECT id, title FROM nc_bases_v2 WHERE id='pys0rzjz5mgwkzy';",
            "SELECT id, title, column_name, uidt, system FROM nc_columns_v2 WHERE fk_model_id='ml7vrxmx5x9y7pu' ORDER BY \"order\" LIMIT 40;",
            "SELECT id, title, type FROM nc_models_v2 WHERE base_id='pys0rzjz5mgwkzy' AND type='table' AND id='ml7vrxmx5x9y7pu';",
            # maybe views table naming
            "\\dt *view*",
        ]:
            run(c, sql)
    finally:
        c.close()


if __name__ == "__main__":
    main()
