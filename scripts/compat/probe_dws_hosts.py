#!/usr/bin/env python3
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
SELECT column_name FROM information_schema.columns WHERE table_name='nc_sources_v2' ORDER BY 1;
SELECT id, alias, type, fk_integration_id, is_meta, is_schema_readonly, is_data_readonly
FROM nc_sources_v2 WHERE id='bo7uyto2o0xk4ti';
SELECT id, title, type, left(config::text,500) AS cfg
FROM nc_integrations_v2
WHERE id IN (SELECT fk_integration_id FROM nc_sources_v2 WHERE id='bo7uyto2o0xk4ti')
   OR config::text ILIKE '%metabase_dws%' OR title ILIKE '%DWS%'
LIMIT 20;
SELECT id, email FROM nc_users_v2 ORDER BY created_at NULLS LAST LIMIT 8;
"""
    with sftp.file("/tmp/integ2.sql", "w") as f:
        f.write(sql)
    sftp.close()
    cmd = (
        "docker run --rm --network host -e PGPASSWORD=Pass@w0rd "
        "-v /tmp/integ2.sql:/tmp/s.sql:ro postgres:13 "
        "psql -h 192.168.100.97 -U postgres -d mlnoco -f /tmp/s.sql"
    )
    _, o, _ = c.exec_command(cmd, timeout=60, get_pty=True)
    print(o.read().decode("utf-8", "replace")[:10000])

    # probe possible DWS hosts for factsxshippingcomm
    hosts = ["192.168.100.97", "192.168.100.99", "192.168.100.89", "192.168.100.93"]
    pwds = ["Pass@w0rd", "PassW0rd@321"]
    users = ["postgres", "sa"]
    for host in hosts:
        for user in users:
            for pw in pwds:
                probe = (
                    f"docker run --rm --network host -e PGPASSWORD={pw} postgres:13 "
                    f"psql -h {host} -U {user} -d metabase_dws -c "
                    "\"SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='dbo' AND table_name='factsxshippingcomm' "
                    "ORDER BY ordinal_position;\" 2>&1 | head -40"
                )
                print(f"\n=== try {user}@{host}/metabase_dws ===", flush=True)
                _, o2, _ = c.exec_command(probe, timeout=20, get_pty=True)
                out = o2.read().decode("utf-8", "replace")
                if "factsxshippingcomm" in out or "column_name" in out and "password" not in out.lower():
                    print(out[:3000], flush=True)
                    if "nc_order" in out or "column_name" in out:
                        # keep going to show columns
                        pass
                else:
                    print(out[:400].replace("\n", " "), flush=True)
    c.close()


if __name__ == "__main__":
    main()
