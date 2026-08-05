#!/usr/bin/env python3
"""Deploy latest mlnocodb (v0.1.3) to test server 192.168.100.89 via Docker."""
from __future__ import annotations

import os
import sys
import tarfile
import time
from pathlib import Path

import paramiko

HOST = "192.168.100.89"
USER = "root"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")
REPO = Path(r"D:\Project\nocodb\mlnocodb")
STAGING = Path(r"D:\mlnocodb-backup\deploy-10089")
REMOTE_DIR = "/opt/mlnocodb"
IMAGE = "mlnocodb:0.1.3"

COMPOSE = f"""services:
  api:
    image: {IMAGE}
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
      - {REMOTE_DIR}/data:/usr/app/data
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
      - {REMOTE_DIR}/ui-output:/app:ro
"""


def run(c, cmd, timeout=600, show=True):
    if show:
        print(f"\n$ {cmd[:240]}")
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if show and out.strip():
        print(out.rstrip()[:4000])
    if code != 0 and err.strip():
        print(err.rstrip()[:1000], file=sys.stderr)
    return code, out, err


def sftp_put(sftp, local: Path, remote: str, progress_every_mb=50):
    size = local.stat().st_size
    print(f"Upload {local.name} ({size/1024/1024:.1f} MiB) -> {remote}")
    last = {"n": 0, "t": time.time()}

    def cb(transferred, total):
        now = time.time()
        if now - last["t"] >= 3 or transferred == total:
            print(f"  ... {transferred/1024/1024:.0f}/{total/1024/1024:.0f} MiB")
            last["t"] = now

    sftp.put(str(local), remote, callback=cb)


def make_tarballs():
    STAGING.mkdir(parents=True, exist_ok=True)
    api_ctx = STAGING / "api-build-context.tar.gz"
    ui_tar = STAGING / "ui-output.tar.gz"

    # API build context: Dockerfile.centos + docker/main.js + src/public
    nocodb = REPO / "packages" / "nocodb"
    print("Packing API build context...")
    with tarfile.open(api_ctx, "w:gz") as tar:
        tar.add(nocodb / "Dockerfile.centos", arcname="Dockerfile.centos")
        # Dockerfile expects COPY docker/main.js and COPY src/public/
        # We'll use a build dir layout matching Dockerfile paths when using -f Dockerfile.centos from packages/nocodb
        tar.add(nocodb / "docker" / "main.js", arcname="docker/main.js")
        tar.add(nocodb / "src" / "public", arcname="src/public")
        # Use 0.301.3 if 0.301.2 missing: include alternate Dockerfile
        alt = (nocodb / "Dockerfile.centos").read_text(encoding="utf-8")
        alt3013 = alt.replace("nocodb/nocodb:0.301.2", "nocodb/nocodb:0.301.3")
        alt_path = STAGING / "Dockerfile.centos.3013"
        alt_path.write_text(alt3013, encoding="utf-8")
        tar.add(alt_path, arcname="Dockerfile.centos.3013")

    print("Packing UI .output...")
    ui_src = REPO / "packages" / "nc-gui" / ".output"
    if not (ui_src / "server" / "index.mjs").exists():
        raise SystemExit("UI .output missing server/index.mjs — build nc-gui first")
    with tarfile.open(ui_tar, "w:gz") as tar:
        # pack contents of .output as ui-output/
        for p in ui_src.rglob("*"):
            if p.is_file():
                tar.add(p, arcname=str(Path("ui-output") / p.relative_to(ui_src)).replace("\\", "/"))

    print(f"API ctx: {api_ctx.stat().st_size/1024/1024:.1f} MiB")
    print(f"UI tar:  {ui_tar.stat().st_size/1024/1024:.1f} MiB")
    return api_ctx, ui_tar


def main():
    api_ctx, ui_tar = make_tarballs()

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting {USER}@{HOST} ...")
    c.connect(HOST, username=USER, password=PWD, timeout=30)
    try:
        run(c, f"mkdir -p {REMOTE_DIR}/build {REMOTE_DIR}/data {REMOTE_DIR}/ui-output /tmp/mlnoco-deploy")

        sftp = c.open_sftp()
        sftp_put(sftp, api_ctx, "/tmp/mlnoco-deploy/api-build-context.tar.gz")
        sftp_put(sftp, ui_tar, "/tmp/mlnoco-deploy/ui-output.tar.gz")
        with sftp.file(f"{REMOTE_DIR}/docker-compose.yml", "w") as f:
            f.write(COMPOSE)
        sftp.close()

        print("\n=== extract ===")
        run(c, f"rm -rf {REMOTE_DIR}/build/*; tar -xzf /tmp/mlnoco-deploy/api-build-context.tar.gz -C {REMOTE_DIR}/build")
        run(c, f"rm -rf {REMOTE_DIR}/ui-output/*; tar -xzf /tmp/mlnoco-deploy/ui-output.tar.gz -C {REMOTE_DIR}")
        run(c, f"ls -la {REMOTE_DIR}/build; test -f {REMOTE_DIR}/ui-output/server/index.mjs && echo UI_OK")

        print("\n=== ensure mlnoco DB ===")
        run(
            c,
            "docker exec postgres psql -U postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='mlnoco'\" | grep -q 1 "
            "|| docker exec postgres psql -U postgres -c \"CREATE DATABASE mlnoco;\"",
        )
        run(c, "docker exec postgres psql -U postgres -d mlnoco -tAc \"select current_database(), count(*) from information_schema.tables where table_schema='public'\"")

        print("\n=== ensure base images ===")
        # Prefer 0.301.2; fallback tag from 0.301.3; try pull with mirrors
        code, out, _ = run(c, "docker images -q nocodb/nocodb:0.301.2")
        if not out.strip():
            print("0.301.2 missing — try pull / retag 0.301.3")
            run(
                c,
                "docker pull nocodb/nocodb:0.301.2 2>&1 || "
                "docker pull docker.m.daocloud.io/nocodb/nocodb:0.301.2 2>&1 && docker tag docker.m.daocloud.io/nocodb/nocodb:0.301.2 nocodb/nocodb:0.301.2; "
                "true",
                timeout=900,
            )
            code, out, _ = run(c, "docker images -q nocodb/nocodb:0.301.2")
            if not out.strip():
                run(c, "docker tag nocodb/nocodb:0.301.3 nocodb/nocodb:0.301.2 && echo RETAGGED_3013_AS_3012")

        code, out, _ = run(c, "docker images -q node:22-slim")
        if not out.strip():
            run(
                c,
                "docker pull node:22-slim 2>&1 || "
                "docker pull docker.m.daocloud.io/library/node:22-slim 2>&1 && docker tag docker.m.daocloud.io/library/node:22-slim node:22-slim",
                timeout=900,
            )

        print("\n=== build mlnocodb:0.1.3 ===")
        # Use Dockerfile.centos; if base pull of mssql npm fails, still ok if network works
        code, out, _ = run(
            c,
            f"cd {REMOTE_DIR}/build && docker build -t {IMAGE} -f Dockerfile.centos . 2>&1",
            timeout=1200,
        )
        if code != 0:
            print("Build with 0.301.2 failed — retry Dockerfile.centos.3013")
            run(c, f"cd {REMOTE_DIR}/build && cp Dockerfile.centos.3013 Dockerfile.centos")
            code, out, _ = run(
                c,
                f"cd {REMOTE_DIR}/build && docker build -t {IMAGE} -f Dockerfile.centos . 2>&1",
                timeout=1200,
            )
            if code != 0:
                print("BUILD FAILED", file=sys.stderr)
                return 1

        run(c, f"docker run --rm {IMAGE} node -e \"require('mssql'); console.log('mssql_ok')\"")

        print("\n=== stop old containers if any ===")
        run(c, "docker rm -f mlnocodb-api mlnocodb-ui 2>/dev/null || true")

        print("\n=== compose up ===")
        code, _, _ = run(c, f"cd {REMOTE_DIR} && docker compose up -d 2>&1")
        if code != 0:
            return 1

        print("\n=== wait boot ===")
        time.sleep(30)
        run(c, "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'")
        run(c, "docker logs --tail 25 mlnocodb-api 2>&1")

        print("\n=== health ===")
        run(c, "curl -s -m 10 -o /dev/null -w 'API_root=%{http_code}\\n' http://127.0.0.1:6080/")
        run(
            c,
            "curl -s -m 10 -X POST http://127.0.0.1:6080/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' -d '{\"email\":\"x@x.com\",\"password\":\"y\"}' | head -c 200; echo",
        )
        run(c, "curl -s -m 10 -o /dev/null -w 'UI=%{http_code}\\n' http://127.0.0.1:6100/")
        run(c, "curl -s -m 10 -o /dev/null -w 'jobs_listen=%{http_code}\\n' -X POST http://127.0.0.1:6080/jobs/listen -H 'Content-Type: application/json' -d '{\"_mid\":0,\"data\":{\"id\":\"x\"}}'")

        print("\n=== cleanup tmp ===")
        run(c, "rm -rf /tmp/mlnoco-deploy")
    finally:
        c.close()
    print("\nDone. UI http://192.168.100.89:6100/  API http://192.168.100.89:6080/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
