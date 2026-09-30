#!/usr/bin/env python3
"""Dig source credentials and whether physical nc_order exists on DWS table."""
from __future__ import annotations

import json
import os
import re

import paramiko

JUMP = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(JUMP, username="root", password=PWD, timeout=30)
    sftp = c.open_sftp()
    sql = r"""
SELECT id, alias, type, length(config::text) AS cfg_len, config::text AS cfg
FROM nc_sources_v2
WHERE id IN ('bo7uyto2o0xk4ti','bam19qz40uvvsnw','bgpscvcf95fnw02');

SELECT id, title, table_name, source_id
FROM nc_models_v2
WHERE id IN ('ml7vrxmx5x9y7pu','m9verevinrhsd41','m32po9hmz81m78t');
"""
    with sftp.file("/tmp/src_cfg.sql", "w") as f:
        f.write(sql)
    sftp.close()
    cmd = (
        "docker run --rm --network host -e PGPASSWORD=Pass@w0rd "
        "-v /tmp/src_cfg.sql:/tmp/s.sql:ro postgres:13 "
        "psql -h 192.168.100.97 -U postgres -d mlnoco -f /tmp/s.sql"
    )
    _, o, _ = c.exec_command(cmd, timeout=60, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    print(out[:10000])

    # Try common DWS hosts from AI prompt / prior knowledge via docker on 89
    # Also try extract host from any source with metabase_dws
    cmd2 = (
        "docker run --rm --network host -e PGPASSWORD=Pass@w0rd postgres:13 "
        "psql -h 192.168.100.97 -U postgres -d mlnoco -tAc "
        "\"SELECT id||'|'||alias||'|'||config::text FROM nc_sources_v2 WHERE config::text ILIKE '%metabase_dws%' OR alias ILIKE '%DWS%';\""
    )
    _, o2, _ = c.exec_command(cmd2, timeout=60, get_pty=True)
    print("=== dws sources ===")
    print(o2.read().decode("utf-8", "replace")[:8000])
    c.close()


if __name__ == "__main__":
    main()
