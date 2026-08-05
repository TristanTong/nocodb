#!/usr/bin/env python3
"""Verify mlnocodb API on 100.93 is connected to PG 100.97."""
import os
import sys

import paramiko

HOST = "192.168.100.93"

CMDS = [
    ("container status", "docker ps -a --format '{{.Names}}\\t{{.Status}}' | grep mlnocodb"),
    ("api restart count", "docker inspect mlnocodb-api --format 'RestartCount={{.RestartCount}} State={{.State.Status}}'"),
    ("api logs all", "docker logs mlnocodb-api 2>&1 | tail -30"),
    ("auth endpoint (expect 400/401 json)",
     "curl -s -m 10 -X POST http://localhost:6080/api/v1/auth/user/signin -H 'Content-Type: application/json' -d '{\"email\":\"nonexistent@x.com\",\"password\":\"wrong\"}'"),
    ("meta bases endpoint (expect 401)",
     "curl -s -m 10 -o /dev/null -w 'bases http_code=%{http_code}' http://localhost:6080/api/v1/db/meta/bases"),
    ("version endpoint",
     "curl -s -m 10 http://localhost:6080/api/v1/version 2>/dev/null | head -c 300; echo"),
]


def main():
    pwd = os.environ.get("REMOTE_SSH_PASSWORD", "")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=pwd, timeout=30)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
