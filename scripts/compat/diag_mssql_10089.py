#!/usr/bin/env python3
"""Compare MSSQL support on local vs Docker 100.89."""
import os
import sys
import json
import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")


def run(c, cmd, timeout=60):
    print(f"\n$ {cmd[:220]}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    print(out.encode("ascii", "replace").decode().rstrip()[:2500], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        print("=== image / container ===", flush=True)
        run(c, "docker ps --filter name=mlnocodb-api --format '{{.Image}} {{.Status}}'")
        run(c, "docker images mlnocodb:0.1.3 --format '{{.ID}} {{.CreatedSince}} {{.Size}}'")

        print("\n=== mssql require inside container ===", flush=True)
        run(c, "docker exec mlnocodb-api node -e \"require('mssql'); console.log('mssql_ok', require.resolve('mssql'))\"")

        print("\n=== client list / supported clients from running app ===", flush=True)
        # check if main.js mentions mssql
        run(c, "docker exec mlnocodb-api sh -c \"grep -o 'mssql' /usr/src/app/docker/main.js | wc -l; ls -la /usr/src/app/node_modules/mssql/package.json 2>&1 | head -3\"")

        print("\n=== try connection-test API without auth (expect 401) then with probe ===", flush=True)
        run(c, "curl -s -m 8 -o /dev/null -w '%{http_code}\\n' -X POST http://127.0.0.1/api/v2/meta/connection/test -H 'Content-Type: application/json' -d '{}'")

        # recent errors in logs
        run(c, "docker logs --since 24h mlnocodb-api 2>&1 | grep -iE 'mssql|sql.?server|not implement|not support|SqlClient' | tail -30")
    finally:
        c.close()


if __name__ == "__main__":
    main()
