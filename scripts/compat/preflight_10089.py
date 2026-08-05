#!/usr/bin/env python3
"""Preflight test server 192.168.100.89 for mlnocodb deploy."""
import os
import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")

CMDS = [
    ("os", "cat /etc/centos-release 2>/dev/null || cat /etc/os-release | head -5"),
    ("docker", "docker --version 2>&1; docker compose version 2>&1"),
    ("containers", "docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' | head -30"),
    ("images mlnocodb", "docker images | grep -iE 'mlnocodb|nocodb|node|nginx' || true"),
    ("ports", "ss -tlnp | grep -E ':(22|80|443|5432|6080|6100)\\s' || true"),
    ("opt", "ls -la /opt/mlnocodb 2>/dev/null || echo NO_DIR"),
    ("pg local", "timeout 5 bash -c '</dev/tcp/127.0.0.1/5432' && echo PG_LOCAL_OK || echo PG_LOCAL_FAIL"),
    ("pg mlnoco", "which psql; PGPASSWORD='Pass@w0rd' psql -h 127.0.0.1 -U postgres -d mlnoco -tAc \"select current_database(), count(*) from information_schema.tables where table_schema='public'\" 2>&1 | head -5"),
    ("disk", "df -h / /opt /var/lib/docker 2>/dev/null | head -10"),
    ("selinux", "getenforce 2>/dev/null || true"),
]


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        for title, cmd in CMDS:
            print(f"\n=== {title}")
            _, o, e = c.exec_command(cmd, timeout=60)
            out = o.read().decode("utf-8", "replace")
            err = e.read().decode("utf-8", "replace")
            if out.strip():
                print(out.rstrip())
            if err.strip() and not out.strip():
                print(err.rstrip())
    finally:
        c.close()


if __name__ == "__main__":
    main()
