#!/usr/bin/env python3
"""Continue deploy: rebuild API image (npmmirror) and start API+UI."""
from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "192.168.100.73")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ["DEPLOY_PASSWORD"]
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "192.168.100.73")
NC_DB = os.environ.get(
    "NC_DB",
    "pg://192.168.100.93:5432?u=postgres&p=Pass%40w0rd&d=mlnoco",
)
REMOTE_BASE = "/opt/mlnocodb"


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=40)
    return c


def run(cmd: str, timeout: int = 2400) -> int:
    print(f"$ {cmd}", flush=True)
    c = connect()
    try:
        # write remote log to avoid local encoding issues
        wrapped = f"bash -lc {repr(cmd + ' > /tmp/mlnocodb-cmd.log 2>&1; echo EXIT:$? >> /tmp/mlnocodb-cmd.log')}"
        # safer:
        full = f"({cmd}) > /tmp/mlnocodb-cmd.log 2>&1; echo __EXIT__:$? >> /tmp/mlnocodb-cmd.log"
        _stdin, stdout, stderr = c.exec_command(full, timeout=timeout)
        stdout.channel.recv_exit_status()
        sftp = c.open_sftp()
        with sftp.open("/tmp/mlnocodb-cmd.log", "r") as f:
            data = f.read().decode("utf-8", errors="replace")
        sftp.close()
        # print ascii-safe
        sys.stdout.buffer.write(data.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.flush()
        for line in data.splitlines()[::-1]:
            if line.startswith("__EXIT__:"):
                code = int(line.split(":", 1)[1])
                if code != 0:
                    raise SystemExit(f"FAILED({code}): {cmd}")
                return code
        raise SystemExit(f"no exit code for: {cmd}")
    finally:
        c.close()


def main():
    # status
    run("docker --version; ls -la /opt/mlnocodb/api/docker/main.js /opt/mlnocodb/ui/server/index.mjs")

    # rebuild API
    run(f"cd {REMOTE_BASE}/api && docker build --no-cache -t mlnocodb:0.1.1 -f Dockerfile .")

    run("docker rm -f mlnocodb-api mlnocodb-ui 2>/dev/null || true")

    run(
        "docker run -d --name mlnocodb-api --restart always "
        "-p 6080:8080 "
        f"-e NC_DB='{NC_DB}' "
        "-e NC_DISABLE_TELE=true "
        f"-e NC_PUBLIC_URL='http://{PUBLIC_HOST}:6080' "
        "-e TZ=Asia/Shanghai "
        f"-v {REMOTE_BASE}/data:/usr/app/data "
        "mlnocodb:0.1.1"
    )

    run("docker pull node:22-slim")
    run(
        "docker run -d --name mlnocodb-ui --restart always "
        "-p 80:6100 "
        "-e NITRO_HOST=0.0.0.0 -e NITRO_PORT=6100 -e PORT=6100 "
        f"-e NUXT_PUBLIC_NC_BACKEND_URL='http://{PUBLIC_HOST}:6080' "
        "-e NUXT_PAGE_TRANSITION_DISABLE=true "
        "-e TZ=Asia/Shanghai "
        f"-v {REMOTE_BASE}/ui:/app:ro "
        "-w /app node:22-slim node server/index.mjs"
    )

    run("sleep 8; docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    run("curl -sS http://127.0.0.1:6080/api/v1/health || true")
    run("curl -sS -o /dev/null -w 'ui=%{http_code}\\n' http://127.0.0.1:80/ || true")
    run("docker logs mlnocodb-api --tail 40 || true")
    run("docker logs mlnocodb-ui --tail 40 || true")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
