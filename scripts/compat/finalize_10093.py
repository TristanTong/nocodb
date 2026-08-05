#!/usr/bin/env python3
"""Persist NAT rules via firewalld direct, restart mlnocodb-api, final verify."""
import os
import sys
import time

import paramiko

HOST = "192.168.100.93"

NAT_RULES = [
    ("172.17.0.0/16", "docker0"),
    ("172.18.0.0/16", "br-57a6a75deaa8"),
    ("172.19.0.0/16", "br-9db71a760b2e"),
    ("172.20.0.0/16", "br-db9bee026689"),
]


def run(c, cmd, timeout=90):
    print(f"$ {cmd}")
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip())
    if err.strip() and code != 0:
        print(err.rstrip(), file=sys.stderr)
    return code, out, err


def main():
    pwd = os.environ.get("REMOTE_SSH_PASSWORD", "")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=pwd, timeout=30)
    try:
        print("=== persist MASQUERADE via firewalld direct (nat)")
        for subnet, br in NAT_RULES:
            run(c, f"firewall-cmd --permanent --direct --add-rule ipv4 nat POSTROUTING 0 -s {subnet} ! -o {br} -j MASQUERADE 2>&1 | tail -1")

        print("\n=== restart mlnocodb-api (apply fixed network)")
        run(c, "docker restart mlnocodb-api")
        print("waiting 40s for boot...")
        time.sleep(40)

        print("\n=== status")
        run(c, "docker ps --format '{{.Names}}\\t{{.Status}}' | grep mlnocodb")
        run(c, "docker inspect mlnocodb-api --format 'RestartCount={{.RestartCount}}'")

        print("\n=== api logs (last 15)")
        run(c, "docker logs --tail 15 mlnocodb-api 2>&1")

        print("\n=== functional checks")
        run(c, "curl -s -m 10 -X POST http://localhost:6080/api/v1/auth/user/signin -H 'Content-Type: application/json' -d '{\"email\":\"nonexistent@x.com\",\"password\":\"wrong\"}' | head -c 300; echo")
        run(c, "curl -s -m 10 -o /dev/null -w 'meta/bases http_code=%{http_code}\\n' http://localhost:6080/api/v1/db/meta/bases")
        run(c, "curl -s -m 10 -o /dev/null -w 'UI http_code=%{http_code}\\n' http://localhost:80/")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
