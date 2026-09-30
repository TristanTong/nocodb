#!/usr/bin/env python3
"""Diagnose Docker overlay2 failure on 100.89."""
from __future__ import annotations

import os
import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")


def run(c, cmd, timeout=120):
    print(f"\n==== {cmd[:140]}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out[-6000:], flush=True)
    if err.strip():
        print("STDERR:", err[-1500:], flush=True)
    print(f"exit={code}", flush=True)
    return code, out, err


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        cmds = [
            "uptime; uname -r; cat /etc/centos-release 2>/dev/null || cat /etc/os-release | head -5",
            "df -h / /var/lib/docker 2>/dev/null; df -i / | head -3",
            "free -h | head -3",
            "systemctl is-active docker; docker info 2>&1 | head -40",
            "docker ps -a --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}' | head -40",
            "cd /opt/mlnocodb && ls -la; test -f docker-compose.yml && grep -nE 'image:|container_name|ports' docker-compose.yml | head -40",
            "dmesg 2>/dev/null | tail -30; journalctl -u docker --no-pager -n 40 2>/dev/null | tail -40",
            "ls /var/lib/docker/overlay2 2>/dev/null | wc -l; "
            "ls -la /var/lib/docker/overlay2/45c6e5682bbd5aaa21e107061bc71c7a24ec79b9a01603123028278d5b891d05 2>&1 | head -20",
            "docker inspect 4a2344411288 2>&1 | head -80",
            "mount | grep overlay | head -20; mount | grep docker | head -20",
        ]
        for cmd in cmds:
            run(c, cmd)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
