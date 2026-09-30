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
_, o, _ = c.exec_command(
    "docker logs --tail 80 mlnocodb-api 2>&1 | tail -50",
    timeout=30,
)
print(o.read().decode("utf-8", "replace"))
c.close()
