#!/usr/bin/env python3
"""Finish compose up and verify on 100.89."""
import os
import sys
import time
import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")


def run(c, cmd, timeout=120):
    print(f"$ {cmd}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    safe = out.encode("ascii", "replace").decode("ascii")
    if safe.strip():
        print(safe.rstrip()[:3000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(c, "cat /opt/mlnocodb/docker-compose.yml")
        run(c, "cd /opt/mlnocodb && docker compose up -d 2>&1")
        time.sleep(30)
        run(c, "docker ps -a --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'")
        run(c, "docker logs --tail 50 mlnocodb-api 2>&1")
        run(c, "docker logs --tail 15 mlnocodb-ui 2>&1")
        run(
            c,
            "curl -s -m 12 -X POST http://127.0.0.1:6080/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' -d '{\"email\":\"a@b.c\",\"password\":\"x\"}'",
        )
        run(c, "curl -s -m 10 -o /dev/null -w 'UI=%{http_code}\\n' http://127.0.0.1:6100/")
        run(c, "docker inspect mlnocodb-api --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'NC_DB|NC_PUBLIC'")
        # test container -> host PG
        run(
            c,
            "docker run --rm --network bridge postgres:15-alpine "
            "nc -z -w5 192.168.100.89 5432 && echo PG_FROM_CTR_OK || echo PG_FROM_CTR_FAIL",
            timeout=60,
        )
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
