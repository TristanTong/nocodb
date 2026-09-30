#!/usr/bin/env python3
"""Get full source config and compare a working Order column meta row."""
from __future__ import annotations

import os
import paramiko

JUMP = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(JUMP, username="root", password=PWD, timeout=30)
    sftp = c.open_sftp()
    sql = """
SELECT id, alias, type, is_meta, is_local, is_schema_readonly, is_data_readonly,
       config::text AS config
FROM nc_sources_v2 WHERE id='bo7uyto2o0xk4ti';

-- sample good Order column meta from same base if any
SELECT c.id, c.fk_model_id, c.title, c.column_name, c.uidt, c.system, c.dt, c.dtx, c.meta,
       c.cdf, c.pk, c.pv, c.rqd, c.un, c.ai, c.au, c.\"order\", c.base_id, c.source_id
FROM nc_columns_v2 c
JOIN nc_models_v2 m ON m.id=c.fk_model_id
WHERE c.uidt='Order' AND m.base_id='pys0rzjz5mgwkzy'
LIMIT 3;

-- view columns for target view
SELECT * FROM nc_grid_view_columns_v2 WHERE fk_view_id='vwncjefh9as7wsyr' LIMIT 5;
SELECT count(*) FROM nc_grid_view_columns_v2 WHERE fk_view_id='vwncjefh9as7wsyr';
"""
    with sftp.file("/tmp/inspect_src.sql", "w") as f:
        f.write(sql)
    sftp.close()
    cmd = (
        "docker run --rm --network host -e PGPASSWORD=Pass@w0rd "
        "-v /tmp/inspect_src.sql:/tmp/s.sql:ro postgres:13 "
        "psql -h 192.168.100.97 -U postgres -d mlnoco -f /tmp/s.sql"
    )
    _, o, _ = c.exec_command(cmd, timeout=60, get_pty=True)
    print(o.read().decode("utf-8", "replace")[:8000])
    c.close()


if __name__ == "__main__":
    main()
