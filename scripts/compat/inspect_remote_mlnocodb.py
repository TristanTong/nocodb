#!/usr/bin/env python3
import json
import os
import paramiko

host = "192.168.100.73"
pwd = os.environ.get("REMOTE_SSH_PASSWORD", "")
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(host, username="root", password=pwd, timeout=30)

cmds = [
    "docker inspect mlnocodb-api mlnocodb-ui",
    "find /opt /root /home -maxdepth 5 -name 'docker-compose*.yml' 2>/dev/null",
    "ls -laR /opt/mlnocodb 2>/dev/null | head -80",
]
for cmd in cmds:
    print("===", cmd)
    _, o, e = c.exec_command(cmd, timeout=120)
    print(o.read().decode("utf-8", "replace"))
    err = e.read().decode("utf-8", "replace")
    if err.strip():
        print(err)
c.close()
