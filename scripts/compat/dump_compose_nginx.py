#!/usr/bin/env python3
import os
import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.100.93", username="root", password=os.environ["REMOTE_SSH_PASSWORD"], timeout=30)
for cmd in [
    "cat /opt/mlnocodb/docker-compose.yml",
    "echo ---NGINX---",
    "cat /opt/mlnocodb/nginx.conf",
]:
    _, o, _ = c.exec_command(cmd, timeout=30)
    print(o.read().decode("utf-8", "replace"), end="")
c.close()
