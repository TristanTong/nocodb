#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "192.168.100.73")
PASSWORD = os.environ["DEPLOY_PASSWORD"]


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PASSWORD, timeout=40)
    cmds = [
        'docker ps --format "table {{.Names}}\\t{{.Status}}\\t{{.Ports}}"',
        "curl -sS http://127.0.0.1:6080/api/v1/health; echo",
        'curl -sS -o /dev/null -w "ui_http=%{http_code}\\n" http://127.0.0.1:80/',
        "curl -sS -I http://127.0.0.1:80/ | head -20",
        "docker logs mlnocodb-ui --tail 40",
        "docker logs mlnocodb-api --tail 20",
        "firewall-cmd --permanent --add-port=80/tcp; firewall-cmd --permanent --add-port=6080/tcp; firewall-cmd --reload; firewall-cmd --list-ports",
    ]
    for cmd in cmds:
        print(f"=== {cmd}", flush=True)
        _stdin, stdout, stderr = c.exec_command(cmd, timeout=90)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
        if err.strip():
            sys.stdout.buffer.write(b"STDERR:\n")
            sys.stdout.buffer.write(err.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.flush()
    c.close()
    print("VERIFY_DONE", flush=True)


if __name__ == "__main__":
    main()
