#!/usr/bin/env python3
"""Hotpatch MSSQL-capable main.js into 100.89 running API and pin compose image."""
from __future__ import annotations

import os
import sys
import time

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")
REMOTE = "/opt/mlnocodb"


def run(c, cmd, timeout=180):
    print(f"\n$ {cmd[:280]}", flush=True)
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    # strip braille spinner chars
    clean = "".join(ch for ch in out if ord(ch) < 0x2800 or ord(ch) > 0x28FF)
    if clean.strip():
        print(clean.rstrip()[:5000], flush=True)
    print(f"exit={code}", flush=True)
    return code, clean


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        # Prefer build/main.js that has MssqlClient
        run(
            c,
            "test -f /opt/mlnocodb/build/docker/main.js && "
            "grep -c MssqlClient /opt/mlnocodb/build/docker/main.js && "
            "wc -c /opt/mlnocodb/build/docker/main.js",
        )
        run(
            c,
            "docker cp /opt/mlnocodb/build/docker/main.js mlnocodb-api:/usr/src/app/docker/main.js",
        )
        run(
            c,
            "docker exec mlnocodb-api sh -c "
            "'wc -c /usr/src/app/docker/main.js; "
            "grep -c MssqlClient /usr/src/app/docker/main.js; "
            "grep -c \"\\\"mssql\\\"===e.client\" /usr/src/app/docker/main.js; "
            "node -e \"require(\\\"mssql\\\"); console.log(\\\"mssql_ok\\\")\"'",
        )
        # Commit as mlnocodb:0.1.3 and retarget compose to tag (not old digest)
        run(c, "docker commit mlnocodb-api mlnocodb:0.1.3")
        run(
            c,
            f"cp -a {REMOTE}/docker-compose.yml {REMOTE}/docker-compose.yml.bak.mssql.$(date +%Y%m%d%H%M%S); "
            f"sed -i 's#image: sha256:d2e3d15a6a68[^ ]*#image: mlnocodb:0.1.3#' {REMOTE}/docker-compose.yml; "
            f"grep -n 'image:' {REMOTE}/docker-compose.yml",
        )
        run(c, f"cd {REMOTE} && docker compose up -d --force-recreate api")
        time.sleep(22)
        run(
            c,
            "docker exec mlnocodb-api sh -c "
            "'echo MssqlClient=$(grep -c MssqlClient /usr/src/app/docker/main.js); "
            "echo branch=$(grep -c \"\\\"mssql\\\"===e.client\" /usr/src/app/docker/main.js); "
            "node -e \"require(\\\"mssql\\\");console.log(\\\"mssql_ok\\\")\"'; "
            "curl -s -m 10 http://127.0.0.1:6080/api/v1/health; echo; "
            "curl -s -m 10 http://127.0.0.1/api/v1/version; echo",
        )
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
