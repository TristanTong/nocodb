#!/usr/bin/env python3
"""Diagnose and hotpatch NocoDB PATCH-500 on 192.168.100.89."""
from __future__ import annotations

import os
import sys
import time

import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("connect", HOST, flush=True)
    c.connect(HOST, username="root", password=PWD, timeout=30, banner_timeout=60)

    def run(cmd: str, timeout: int = 120) -> tuple[int, str]:
        print("$", cmd[:240], flush=True)
        _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
        out = o.read().decode("utf-8", "replace")
        code = o.channel.recv_exit_status()
        if out.strip():
            print(out.rstrip()[:4000], flush=True)
        print(" exit=", code, flush=True)
        return code, out

    run("docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'")
    run("docker exec mlnocodb-api node -e \"console.log(process.env.NODE_ENV||'unset'); console.log(require('/usr/src/app/package.json').version||'no')\" 2>/dev/null || docker exec mlnocodb-api sh -c 'ls /usr/src/app 2>/dev/null; ls /usr/app 2>/dev/null; find / -name main.js 2>/dev/null | head'")

    # locate bundle
    code, out = run(
        "docker exec mlnocodb-api sh -c \"find /usr -name 'main.js' 2>/dev/null | head -20; ls -la /usr/src/app/docker 2>/dev/null; ls -la /usr/app 2>/dev/null\""
    )

    # grep AI strip pattern in container
    run(
        "docker exec mlnocodb-api sh -c \"grep -n 'Never write AI/IDENTITY\\|isInsertData && !extra\\|pkColumn.ai' /usr/src/app/docker/main.js 2>/dev/null | head -20; grep -n 'Never write AI/IDENTITY\\|pkColumn.ai' /usr/app/main.js 2>/dev/null | head -20\""
    )

    # nginx
    run("nginx -T 2>/dev/null | grep -E 'server_name|proxy_pass|listen|6080' | head -40")

    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
