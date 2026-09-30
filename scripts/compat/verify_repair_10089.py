#!/usr/bin/env python3
import os
import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(
    "192.168.100.89",
    username="root",
    password=os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd"),
    timeout=25,
)
cmd = r"""
docker ps --filter name=mlnocodb --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
echo VERSION=$(curl -s http://127.0.0.1:6080/api/v1/version)
echo HEALTH=$(curl -s http://127.0.0.1:6080/api/v1/health)
echo NGINX=$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1/)
echo UI=$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:6100/)
docker exec mlnocodb-api node -e "require('mssql');console.log('mssql_ok')"
grep -n 'image:' /opt/mlnocodb/docker-compose.yml
"""
_, o, e = c.exec_command(cmd, timeout=60)
print(o.read().decode("utf-8", "replace"))
err = e.read().decode("utf-8", "replace")
if err.strip():
    print("ERR", err[-300:])
c.close()
