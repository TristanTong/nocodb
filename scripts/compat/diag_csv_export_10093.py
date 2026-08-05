#!/usr/bin/env python3
"""Diagnose CSV export stuck on Preparing: jobs, socket.io, nginx, logs."""
import json
import os
import sys
import urllib.parse

import paramiko

HOST = "192.168.100.93"
EMAIL = os.environ.get("NC_TEST_EMAIL", "mssql-ui-test@local.test")
PASSWORD = os.environ.get("NC_TEST_PASSWORD", "TestPass@12345")
# view from user URL: .../phr43fj3yvo56qr/mn6pd42obixv08z/vwfdauan1nf2yh6c
VIEW_ID = "vwfdauan1nf2yh6c"
BASE_ID = "phr43fj3yvo56qr"


def run(c, cmd, timeout=90):
    print(f"$ {cmd[:180]}{'...' if len(cmd)>180 else ''}")
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
    pwd = os.environ["REMOTE_SSH_PASSWORD"]
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=pwd, timeout=30)
    try:
        print("=== containers ===")
        run(c, "docker ps --filter name=mlnocodb --format '{{.Names}}\\t{{.Status}}\\t{{.Ports}}'")

        print("\n=== redis / NC_REDIS in api env ===")
        run(c, "docker inspect mlnocodb-api --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -iE 'REDIS|JOB' || echo NO_REDIS_ENV")

        print("\n=== socket.io via nginx (HTTP handshake) ===")
        run(c, "curl -s -m 8 -o /tmp/sio.txt -w 'http=%{http_code}\\n' 'http://127.0.0.1/socket.io/?EIO=4&transport=polling'; head -c 200 /tmp/sio.txt; echo")
        run(c, "curl -s -m 8 -o /tmp/sio2.txt -w 'http=%{http_code}\\n' 'http://127.0.0.1:6080/socket.io/?EIO=4&transport=polling'; head -c 200 /tmp/sio2.txt; echo")

        print("\n=== login + trigger export ===")
        # signin
        login_cmd = (
            "curl -s -m 15 -X POST http://127.0.0.1:6080/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' "
            f"-d '{{\"email\":\"{EMAIL}\",\"password\":\"{PASSWORD}\"}}'"
        )
        code, out, _ = run(c, login_cmd)
        try:
            token = json.loads(out).get("token")
        except Exception:
            token = None
        if not token:
            print("LOGIN_FAILED, try listing users / alt login")
            # try without specific user - list first user emails from pg
            run(
                c,
                "timeout 20 docker run --rm --network mlnocodb_default postgres:15-alpine "
                "psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco?connect_timeout=5' "
                "-tAc \"select email from nc_users_v2 order by created_at limit 8\" 2>&1",
            )
            return 1

        print(f"token_len={len(token)}")

        # postOperation dataExport - find workspace id from meta
        run(
            c,
            "timeout 20 docker run --rm --network mlnocodb_default postgres:15-alpine "
            "psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco?connect_timeout=5' "
            f"-tAc \"select id, title, fk_workspace_id from nc_bases_v2 where id='{BASE_ID}' or id like '%{BASE_ID}%' limit 5\" 2>&1",
        )

        # Try direct export endpoint
        export_cmd = (
            f"curl -s -m 30 -X POST 'http://127.0.0.1:6080/api/v2/export/{VIEW_ID}/csv' "
            f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' -d '{{}}'"
        )
        code, out, _ = run(c, export_cmd)
        print(f"export_resp={out[:500]}")

        # Also try via nginx
        export_cmd2 = (
            f"curl -s -m 30 -X POST 'http://127.0.0.1/api/v2/export/{VIEW_ID}/csv' "
            f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' -d '{{}}'"
        )
        code, out2, _ = run(c, export_cmd2)
        print(f"export_via_nginx={out2[:500]}")

        print("\n=== api logs after export ===")
        run(c, "docker logs --tail 40 mlnocodb-api 2>&1 | grep -iE 'export|job|error|fail|socket|redis' | tail -30")

        print("\n=== nginx error log ===")
        run(c, "docker logs --tail 20 mlnocodb-nginx 2>&1")

        print("\n=== data dir (exports storage) ===")
        run(c, "ls -la /opt/mlnocodb/data/; find /opt/mlnocodb/data -type f 2>/dev/null | head -30; du -sh /opt/mlnocodb/data")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
