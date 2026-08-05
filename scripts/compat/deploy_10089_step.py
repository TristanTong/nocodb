#!/usr/bin/env python3
"""Stepwise deploy to 100.89 — unbuffered, reuses local tarballs."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

sys.stdout.reconfigure(line_buffering=True)

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")
STAGING = Path(r"D:\mlnocodb-backup\deploy-10089")
REMOTE = "/opt/mlnocodb"
IMAGE = "mlnocodb:0.1.3"

COMPOSE = """services:
  api:
    image: mlnocodb:0.1.3
    container_name: mlnocodb-api
    restart: always
    ports:
      - "6080:8080"
    environment:
      NC_DB: "pg://192.168.100.89:5432?u=postgres&p=Pass%40w0rd&d=mlnoco"
      NC_DISABLE_TELE: "true"
      NC_PUBLIC_URL: "http://192.168.100.89:6080"
      TZ: Asia/Shanghai
    volumes:
      - /opt/mlnocodb/data:/usr/app/data
    extra_hosts:
      - "host.docker.internal:host-gateway"

  ui:
    image: node:22-slim
    container_name: mlnocodb-ui
    restart: always
    working_dir: /app
    command: ["node", "server/index.mjs"]
    ports:
      - "6100:6100"
    environment:
      PORT: "6100"
      NITRO_HOST: "0.0.0.0"
      NITRO_PORT: "6100"
      NUXT_PUBLIC_NC_BACKEND_URL: "http://192.168.100.89:6080"
      NUXT_PAGE_TRANSITION_DISABLE: "true"
      TZ: Asia/Shanghai
    volumes:
      - /opt/mlnocodb/ui-output:/app:ro
"""


def run(c, cmd, timeout=600):
    print(f"$ {cmd[:220]}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    # stream-ish: wait then read
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip()[:3500], flush=True)
    print(f"  exit={code}", flush=True)
    return code, out


def main():
    api_tar = STAGING / "api-build-context.tar.gz"
    ui_tar = STAGING / "ui-output.tar.gz"
    assert api_tar.exists() and ui_tar.exists(), "missing tarballs"

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("connect...", flush=True)
    c.connect(HOST, username="root", password=PWD, timeout=30, banner_timeout=60)
    print("connected", flush=True)

    try:
        run(c, f"mkdir -p {REMOTE}/build {REMOTE}/data {REMOTE}/ui-output /tmp/mlnoco-deploy")

        print("sftp upload...", flush=True)
        sftp = c.open_sftp()
        for local, remote in [
            (api_tar, "/tmp/mlnoco-deploy/api-build-context.tar.gz"),
            (ui_tar, "/tmp/mlnoco-deploy/ui-output.tar.gz"),
        ]:
            print(f"  put {local.name} ({local.stat().st_size/1024/1024:.1f}MB)", flush=True)
            t0 = time.time()
            sftp.put(str(local), remote)
            print(f"  done in {time.time()-t0:.1f}s", flush=True)
        with sftp.file(f"{REMOTE}/docker-compose.yml", "w") as f:
            f.write(COMPOSE)
        sftp.close()
        print("upload ok", flush=True)

        run(c, f"rm -rf {REMOTE}/build/*; tar -xzf /tmp/mlnoco-deploy/api-build-context.tar.gz -C {REMOTE}/build")
        run(c, f"rm -rf {REMOTE}/ui-output; tar -xzf /tmp/mlnoco-deploy/ui-output.tar.gz -C {REMOTE}; test -f {REMOTE}/ui-output/server/index.mjs && echo UI_OK")

        run(
            c,
            "docker exec postgres psql -U postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='mlnoco'\" | grep -q 1 "
            "|| docker exec postgres psql -U postgres -c 'CREATE DATABASE mlnoco'",
        )
        run(c, "docker exec postgres psql -U postgres -d mlnoco -tAc \"select current_database()\"")

        # Use existing 0.301.3 as base (already on disk)
        run(c, "docker images nocodb/nocodb --format '{{.Tag}} {{.ID}} {{.Size}}'")
        run(c, "docker tag nocodb/nocodb:0.301.3 nocodb/nocodb:0.301.2 2>/dev/null; docker images -q nocodb/nocodb:0.301.2")

        # Prefer Dockerfile that uses whatever we have
        run(c, f"cp {REMOTE}/build/Dockerfile.centos.3013 {REMOTE}/build/Dockerfile.centos")

        # node:22-slim — try local / pull with short timeout via daoCloud
        code, out = run(c, "docker images -q node:22-slim")
        if not out.strip():
            print("pulling node:22-slim via daocloud...", flush=True)
            code, out = run(
                c,
                "docker pull docker.m.daocloud.io/library/node:22-slim && docker tag docker.m.daocloud.io/library/node:22-slim node:22-slim",
                timeout=600,
            )
            if code != 0:
                run(c, "docker pull node:22-slim", timeout=600)

        print("building image (mssql npm install needs network)...", flush=True)
        code, out = run(
            c,
            f"cd {REMOTE}/build && docker build --network=host -t {IMAGE} -f Dockerfile.centos .",
            timeout=900,
        )
        if code != 0:
            print("BUILD FAILED", flush=True)
            return 1

        run(c, f"docker run --rm {IMAGE} node -e \"require('mssql'); console.log('mssql_ok')\"")
        run(c, "docker rm -f mlnocodb-api mlnocodb-ui 2>/dev/null || true")
        code, _ = run(c, f"cd {REMOTE} && docker compose up -d")
        if code != 0:
            return 1

        time.sleep(25)
        run(c, "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'")
        run(c, "docker logs --tail 30 mlnocodb-api 2>&1")
        run(c, "curl -s -m 10 -X POST http://127.0.0.1:6080/api/v1/auth/user/signin -H 'Content-Type: application/json' -d '{\"email\":\"a@b.c\",\"password\":\"x\"}' | head -c 220; echo")
        run(c, "curl -s -m 10 -o /dev/null -w 'UI=%{http_code}\\n' http://127.0.0.1:6100/")
        run(c, "rm -rf /tmp/mlnoco-deploy")
        print("DONE", flush=True)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
