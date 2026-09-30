#!/usr/bin/env python3
import os
import time
import paramiko

# restart prod api
p = paramiko.SSHClient()
p.set_missing_host_key_policy(paramiko.AutoAddPolicy())
p.connect(
    "192.168.100.93",
    username="root",
    password=os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025"),
    timeout=30,
)
_, o, _ = p.exec_command(
    "cd /opt/mlnocodb && docker compose restart api > /tmp/restart_api.log 2>&1; echo EXIT:$?; tail -5 /tmp/restart_api.log | tr -cd '\\11\\12\\15\\40-\\176'",
    timeout=60,
)
print(o.read().decode("ascii", "replace"))
time.sleep(18)
_, o2, _ = p.exec_command("curl -s -m 10 http://127.0.0.1/api/v1/health; echo", timeout=20)
print(o2.read().decode("ascii", "replace"))
p.close()

# verify meta
j = paramiko.SSHClient()
j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
j.connect(
    "192.168.100.89",
    username="root",
    password=os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd"),
    timeout=30,
)
_, o3, _ = j.exec_command(
    "docker run --rm --network host -e PGPASSWORD=Pass@w0rd postgres:13 "
    "psql -h 192.168.100.97 -U postgres -d mlnoco -c "
    "\"SELECT id,uidt,system FROM nc_columns_v2 WHERE fk_model_id='ml7vrxmx5x9y7pu' AND column_name='nc_order';\"",
    timeout=60,
)
print(o3.read().decode("ascii", "replace"))
j.close()
