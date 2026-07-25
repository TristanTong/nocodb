#!/usr/bin/env python3
"""Switch production Meta DB host 89 -> 93 and verify."""
from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "192.168.100.73")
PASSWORD = os.environ["DEPLOY_PASSWORD"]
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "192.168.100.73")
NC_DB = os.environ.get(
    "NC_DB",
    "pg://192.168.100.93:5432?u=postgres&p=Pass%40w0rd&d=mlnoco",
)
REMOTE_BASE = "/opt/mlnocodb"


def run(c, cmd: str, timeout: int = 120) -> tuple[int, str, str]:
    print(f"$ {cmd}", flush=True)
    _stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out:
        sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if err.strip():
        sys.stdout.buffer.write(b"STDERR:\n")
        sys.stdout.buffer.write(err.encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(b"\n")
    sys.stdout.flush()
    return code, out, err


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PASSWORD, timeout=40)

    # connectivity probe (timeout/nc)
    run(
        c,
        "timeout 5 bash -c 'cat < /dev/null > /dev/tcp/192.168.100.93/5432' "
        "&& echo TCP_93_OK || echo TCP_93_FAIL",
    )
    run(
        c,
        "timeout 5 bash -c 'cat < /dev/null > /dev/tcp/192.168.100.89/5432' "
        "&& echo TCP_89_OK || echo TCP_89_FAIL",
    )

    # show current NC_DB before change
    run(
        c,
        "docker inspect mlnocodb-api --format '{{range .Config.Env}}{{println .}}{{end}}' "
        "| grep '^NC_DB=' || true",
    )

    run(c, "docker rm -f mlnocodb-api 2>/dev/null || true")

    run_cmd = (
        "docker run -d --name mlnocodb-api --restart always "
        "-p 6080:8080 "
        f"-e NC_DB='{NC_DB}' "
        "-e NC_DISABLE_TELE=true "
        f"-e NC_PUBLIC_URL='http://{PUBLIC_HOST}:6080' "
        "-e TZ=Asia/Shanghai "
        f"-v {REMOTE_BASE}/data:/usr/app/data "
        "mlnocodb:0.1.1"
    )
    code, _, _ = run(c, run_cmd)
    if code != 0:
        raise SystemExit("failed to start mlnocodb-api")

    run(c, "sleep 10")
    run(c, "docker ps --filter name=mlnocodb-api --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    run(
        c,
        "docker inspect mlnocodb-api --format '{{range .Config.Env}}{{println .}}{{end}}' "
        "| grep '^NC_DB='",
    )
    run(c, "curl -sS http://127.0.0.1:6080/api/v1/health; echo")
    run(c, "docker logs mlnocodb-api --tail 50")

    c.close()
    print("SWITCH_DONE", flush=True)


if __name__ == "__main__":
    main()
