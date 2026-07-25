#!/usr/bin/env python3
"""Upload artifacts and start mlnocodb API(6080) + UI(80) on CentOS."""
from __future__ import annotations

import os
import sys
import tarfile
import tempfile
from pathlib import Path

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "192.168.100.73")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ["DEPLOY_PASSWORD"]
ROOT = Path(os.environ.get("REPO_ROOT", r"D:\Project\nocodb\mlnocodb"))
API_DIR = ROOT / "deploy-dist" / "api"
UI_SRC = ROOT / "packages" / "nc-gui" / ".output"
REMOTE_BASE = "/opt/mlnocodb"

NC_DB = os.environ.get(
    "NC_DB",
    "pg://192.168.100.93:5432?u=postgres&p=Pass%40w0rd&d=mlnoco",
)
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "192.168.100.73")


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=40)
    return c


def run(cmd: str, timeout: int = 1800) -> int:
    print(f"$ {cmd}", flush=True)
    c = connect()
    try:
        _stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout, get_pty=True)
        for line in iter(stdout.readline, ""):
            sys.stdout.write(line)
            sys.stdout.flush()
        err = stderr.read().decode("utf-8", errors="replace")
        if err.strip():
            sys.stderr.write(err)
        code = stdout.channel.recv_exit_status()
        if code != 0:
            raise SystemExit(f"FAILED({code}): {cmd}")
        return code
    finally:
        c.close()


def upload_tar(local_dir: Path, remote_parent: str, arcname: str):
    if not local_dir.exists():
        raise SystemExit(f"missing {local_dir}")
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        print(f"TAR {local_dir} as {arcname}", flush=True)
        with tarfile.open(tmp_path, "w:gz") as tar:
            tar.add(str(local_dir), arcname=arcname)
        remote_tar = f"/tmp/{tmp_path.name}"
        c = connect()
        try:
            sftp = c.open_sftp()
            print(f"UPLOAD -> {remote_tar} ({tmp_path.stat().st_size} bytes)", flush=True)
            sftp.put(str(tmp_path), remote_tar)
            sftp.close()
        finally:
            c.close()
        run(f"mkdir -p {remote_parent} && tar -xzf {remote_tar} -C {remote_parent} && rm -f {remote_tar}")
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def main():
    if not (API_DIR / "docker" / "main.js").exists():
        raise SystemExit("API main.js missing; run docker:build first")
    if not (UI_SRC / "server" / "index.mjs").exists():
        raise SystemExit("UI .output missing; run nc-gui build first")

    run(f"mkdir -p {REMOTE_BASE}/data {REMOTE_BASE}/api {REMOTE_BASE}/ui")
    upload_tar(API_DIR, REMOTE_BASE, "api")
    # UI: upload .output contents into /opt/mlnocodb/ui
    upload_tar(UI_SRC, REMOTE_BASE, "ui")

    # firewall
    run(
        "firewall-cmd --state >/dev/null 2>&1 && "
        "firewall-cmd --permanent --add-port=80/tcp && "
        "firewall-cmd --permanent --add-port=6080/tcp && "
        "firewall-cmd --reload || true"
    )

    # stop old containers
    run(
        "docker rm -f mlnocodb-api mlnocodb-ui 2>/dev/null || true"
    )

    # build API image on server
    run(
        f"cd {REMOTE_BASE}/api && docker build -t mlnocodb:0.1.1 -f Dockerfile ."
    )

    # start API
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

    # pull node image for UI if needed, then start UI on host port 80
    run("docker pull node:22-slim")
    run(
        "docker run -d --name mlnocodb-ui --restart always "
        "-p 80:6100 "
        "-e NITRO_HOST=0.0.0.0 "
        "-e NITRO_PORT=6100 "
        "-e PORT=6100 "
        f"-e NUXT_PUBLIC_NC_BACKEND_URL='http://{PUBLIC_HOST}:6080' "
        "-e NUXT_PAGE_TRANSITION_DISABLE=true "
        "-e TZ=Asia/Shanghai "
        f"-v {REMOTE_BASE}/ui:/app:ro "
        "-w /app "
        "node:22-slim "
        "node server/index.mjs"
    )

    run("sleep 5; docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    run("curl -sS http://127.0.0.1:6080/api/v1/health || true")
    run("curl -sS -o /dev/null -w 'ui_http=%{http_code}\\n' http://127.0.0.1:80/ || true")
    print("DEPLOY DONE", flush=True)


if __name__ == "__main__":
    main()
