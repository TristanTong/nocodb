#!/usr/bin/env python3
"""Install Docker on remote CentOS via Aliyun mirror."""
import paramiko
import sys
import os

HOST = os.environ.get("DEPLOY_HOST", "192.168.100.73")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ["DEPLOY_PASSWORD"]
LOCAL_SCRIPT = os.environ.get(
    "INSTALL_SCRIPT",
    r"D:\Project\nocodb\mlnocodb\scripts\compat\centos_install_docker.sh",
)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=30)
sftp = c.open_sftp()
sftp.put(LOCAL_SCRIPT, "/tmp/centos_install_docker.sh")
sftp.close()

cmd = "sed -i 's/\\r$//' /tmp/centos_install_docker.sh && bash /tmp/centos_install_docker.sh"
print("RUN:", cmd, flush=True)
stdin, stdout, stderr = c.exec_command(cmd, timeout=1200)
for line in iter(stdout.readline, ""):
    sys.stdout.write(line)
    sys.stdout.flush()
err = stderr.read().decode("utf-8", errors="replace")
if err:
    sys.stderr.write(err)
code = stdout.channel.recv_exit_status()
c.close()
raise SystemExit(code)
