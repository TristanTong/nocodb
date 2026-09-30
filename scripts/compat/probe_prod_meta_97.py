#!/usr/bin/env python3
import os
import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(
    "192.168.100.89",
    username="root",
    password=os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd"),
    timeout=30,
)
cmds = [
    "docker run --rm --network host -e PGPASSWORD=Pass@w0rd postgres:13 "
    "psql -h 192.168.100.97 -U postgres -d mlnoco -c "
    "\"SELECT uidt, count(*) FROM nc_columns_v2 WHERE column_name='nc_order' GROUP BY uidt;\"",
    "docker run --rm --network host -e PGPASSWORD=Pass@w0rd postgres:13 "
    "psql -h 192.168.100.97 -U postgres -d mlnoco -tAc "
    "\"SELECT count(*) FROM nc_models_v2 WHERE type='table'; "
    "SELECT count(*) FROM nc_bases_v2;\"",
]
for cmd in cmds:
    print("$", cmd[:120])
    _, o, _ = c.exec_command(cmd, timeout=90, get_pty=True)
    print(o.read().decode("utf-8", "replace"))
c.close()
