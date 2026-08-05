#!/usr/bin/env python3
"""Pre-flight checks on target host 192.168.100.93 before mlnocodb deploy."""
import os
import sys

import paramiko

HOST = "192.168.100.93"

CMDS = [
    ("docker version", "docker --version && docker info --format 'Server: {{.ServerVersion}} Driver: {{.Driver}}'"),
    ("compose plugin", "docker compose version 2>/dev/null || docker-compose --version 2>/dev/null || echo NO_COMPOSE"),
    ("running containers", "docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'"),
    ("port 80/6080 listeners", "ss -tlnp | grep -E ':(80|6080)\\s' || echo PORTS_FREE"),
    ("selinux", "getenforce 2>/dev/null || echo NO_SELINUX"),
    ("pg 100.97 tcp", "timeout 5 bash -c '</dev/tcp/192.168.100.97/5432' && echo PG_TCP_OK || echo PG_TCP_FAIL"),
    ("psql client", "which psql || echo NO_PSQL"),
    ("disk space", "df -h /opt /var/lib/docker | sed -n '1p;2p;3p'"),
    ("existing mlnocodb dir", "ls -la /opt/mlnocodb 2>/dev/null || echo NO_DIR"),
]


def main():
    pwd = os.environ.get("REMOTE_SSH_PASSWORD", "")
    if not pwd:
        print("REMOTE_SSH_PASSWORD required", file=sys.stderr)
        return 2
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=pwd, timeout=30)
    try:
        for title, cmd in CMDS:
            print(f"\n=== {title}")
            _, o, e = c.exec_command(cmd, timeout=60)
            out = o.read().decode("utf-8", "replace")
            err = e.read().decode("utf-8", "replace")
            code = o.channel.recv_exit_status()
            if out.strip():
                print(out.rstrip())
            if err.strip() and code != 0:
                print(err.rstrip())
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
