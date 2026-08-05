#!/usr/bin/env python3
import os, paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.100.89", username="root", password=os.environ.get("REMOTE_SSH_PASSWORD","Pass@w0rd"), timeout=30)
_, o, _ = c.exec_command("ps aux | grep -E 'docker build|buildkit' | grep -v grep; echo '---'; wc -l /tmp/mlnoco-mssql-fix.log 2>/dev/null; tail -30 /tmp/mlnoco-mssql-fix.log 2>/dev/null; echo '---'; docker images mlnocodb --format '{{.Tag}} {{.ID}} {{.CreatedSince}}'", timeout=30)
print(o.read().decode("utf-8","replace"))
c.close()
