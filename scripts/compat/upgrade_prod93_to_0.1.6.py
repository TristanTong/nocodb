#!/usr/bin/env python3
"""Upgrade 100.93 to mlnocodb:0.1.6 with minimal downtime.

Online (no outage): build on 89 → transfer tar → backup old image/compose on 93 → docker load
Brief outage: patch compose image tag → recreate api only → health check

Usage:
  python scripts/compat/upgrade_prod93_to_0.1.6.py
  python scripts/compat/upgrade_prod93_to_0.1.6.py --phase build
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import paramiko

try:
    from scp import SCPClient
except ImportError:
    SCPClient = None  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
MAIN_JS = ROOT / "packages" / "nocodb" / "docker" / "main.js"
DOCKERFILE = ROOT / "packages" / "nocodb" / "Dockerfile.centos"
PUBLIC_DIR = ROOT / "packages" / "nocodb" / "src" / "public"

HOST89 = "192.168.100.89"
HOST93 = "192.168.100.93"
PWD89 = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")
PWD93 = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")
USER = "root"

TAG = "0.1.6"
IMAGE = f"mlnocodb:{TAG}"
REMOTE_BUILD = f"/tmp/mlnocodb-build-{TAG}"
REMOTE_TAR_89 = f"/opt/mlnocodb/mlnocodb-{TAG}.tar.gz"
REMOTE_TAR_93 = f"/opt/mlnocodb/mlnocodb-{TAG}.tar.gz"
BACKUP_DIR = f"/opt/mlnocodb/backup-pre-{TAG}"


def ssh(host: str, pwd: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username=USER, password=pwd, timeout=30, banner_timeout=60)
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 600, check: bool = True) -> tuple[int, str, str]:
    print(f"  $ {cmd[:200]}{'…' if len(cmd) > 200 else ''}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out[-5000:], end="" if out.endswith("\n") else "\n", flush=True)
    if err.strip() and (code != 0 or "error" in err.lower()):
        print("STDERR:", err[-2000:], flush=True)
    if check and code != 0:
        raise RuntimeError(f"exit {code}: {cmd}\n{err[-800:]}\n{out[-400:]}")
    return code, out, err


def sftp_put(c: paramiko.SSHClient, local: Path, remote: str) -> None:
    print(f"  put {local.name} -> {remote} ({local.stat().st_size} bytes)", flush=True)
    if SCPClient is not None:
        with SCPClient(c.get_transport()) as scp:
            scp.put(str(local), remote)
        return
    sftp = c.open_sftp()
    try:
        sftp.put(str(local), remote)
    finally:
        sftp.close()


def sftp_put_dir(c: paramiko.SSHClient, local: Path, remote: str) -> None:
    run(c, f"mkdir -p {remote}")
    sftp = c.open_sftp()
    try:
        for root, _dirs, files in os.walk(local):
            rel = os.path.relpath(root, local).replace("\\", "/")
            rdir = remote if rel == "." else f"{remote}/{rel}"
            run(c, f"mkdir -p {rdir}", check=False)
            for fn in files:
                lp = Path(root) / fn
                rp = f"{rdir}/{fn}"
                print(f"  put {lp.relative_to(local)}", flush=True)
                sftp.put(str(lp), rp)
    finally:
        sftp.close()


def phase_build_on_89() -> None:
    if not MAIN_JS.is_file():
        raise SystemExit(f"missing {MAIN_JS}")
    text = MAIN_JS.read_text(encoding="utf-8", errors="replace")
    for needle in ("MssqlClient", "Primary key is required to delete records"):
        if needle not in text:
            raise SystemExit(f"main.js missing marker: {needle}")
    print(f"[build] main.js={MAIN_JS.stat().st_size}", flush=True)

    c = ssh(HOST89, PWD89)
    try:
        run(c, f"rm -rf {REMOTE_BUILD} && mkdir -p {REMOTE_BUILD}/docker {REMOTE_BUILD}/src")
        sftp_put(c, MAIN_JS, f"{REMOTE_BUILD}/docker/main.js")
        sftp_put(c, DOCKERFILE, f"{REMOTE_BUILD}/Dockerfile.centos")
        if PUBLIC_DIR.is_dir():
            sftp_put_dir(c, PUBLIC_DIR, f"{REMOTE_BUILD}/src/public")
        else:
            run(c, f"mkdir -p {REMOTE_BUILD}/src/public && touch {REMOTE_BUILD}/src/public/.keep")

        run(c, "docker images --format '{{.Repository}}:{{.Tag}}' | head -30", check=False)
        run(c, f"cd {REMOTE_BUILD} && docker build -t {IMAGE} -f Dockerfile.centos .", timeout=1800)
        run(
            c,
            "docker run --rm "
            + IMAGE
            + " node -e \"require('mssql');console.log('mssql_ok');"
            "var fs=require('fs');var t=fs.readFileSync('/usr/src/app/docker/main.js','utf8');"
            "console.log('MssqlClient',(t.match(/MssqlClient/g)||[]).length);\"",
            timeout=120,
        )
        run(c, "mkdir -p /opt/mlnocodb")
        run(c, f"docker save {IMAGE} | gzip -c > {REMOTE_TAR_89}", timeout=900)
        run(c, f"ls -lh {REMOTE_TAR_89}")
    finally:
        c.close()


def phase_backup_93() -> None:
    c = ssh(HOST93, PWD93)
    try:
        run(c, "docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}' | head -25", check=False)
        run(c, "free -h | head -3; df -h / /opt | head -5", check=False)
        run(c, f"mkdir -p {BACKUP_DIR}")

        run(
            c,
            f"cd /opt/mlnocodb && "
            f"cp -a docker-compose.yml {BACKUP_DIR}/docker-compose.yml 2>/dev/null || true; "
            f"cp -a docker-compose.yml docker-compose.yml.bak.pre-{TAG}-$(date +%Y%m%d%H%M%S) 2>/dev/null || true; "
            f"ls -la docker-compose.yml* | head -15",
            check=False,
        )

        # Pin rollback tag from currently running container
        run(
            c,
            "set -e; "
            "IMG=$(docker inspect -f '{{.Config.Image}}' mlnocodb-api); "
            "ID=$(docker inspect -f '{{.Image}}' mlnocodb-api); "
            "echo running=$IMG id=$ID; "
            f"docker tag \"$ID\" mlnocodb:0.1.1-pre-{TAG}; "
            f"docker tag \"$ID\" mlnocodb:0.1.1 2>/dev/null || true; "
            "docker images --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}' | grep mlnocodb | head -20",
        )

        run(
            c,
            f"if [ ! -s {BACKUP_DIR}/mlnocodb-0.1.1-pre-{TAG}.tar.gz ]; then "
            f"  echo saving_old_image…; "
            f"  docker save mlnocodb:0.1.1-pre-{TAG} | gzip -c > {BACKUP_DIR}/mlnocodb-0.1.1-pre-{TAG}.tar.gz; "
            f"fi; ls -lh {BACKUP_DIR}/",
            timeout=1200,
        )
    finally:
        c.close()


def phase_xfer() -> None:
    c93 = ssh(HOST93, PWD93)
    try:
        code, out, _ = run(c93, f"if [ -s {REMOTE_TAR_93} ]; then ls -lh {REMOTE_TAR_93}; else echo MISSING; fi", check=False)
        if "MISSING" not in out:
            print("[xfer] already present on 93", flush=True)
            return
    finally:
        c93.close()

    # Prefer direct LAN scp 89→93 with sshpass
    c93 = ssh(HOST93, PWD93)
    try:
        code, out, _ = run(
            c93,
            "command -v sshpass || (yum install -y sshpass 2>/dev/null || apt-get install -y sshpass 2>/dev/null); "
            "command -v sshpass",
            check=False,
            timeout=180,
        )
        if code == 0 and "sshpass" in out:
            run(
                c93,
                f"sshpass -p '{PWD89}' scp -o StrictHostKeyChecking=no "
                f"root@{HOST89}:{REMOTE_TAR_89} {REMOTE_TAR_93}",
                timeout=1200,
            )
            run(c93, f"ls -lh {REMOTE_TAR_93}")
            return
    finally:
        c93.close()

    print("[xfer] bridging via local SFTP…", flush=True)
    c89 = ssh(HOST89, PWD89)
    c93 = ssh(HOST93, PWD93)
    try:
        run(c93, "mkdir -p /opt/mlnocodb")
        s89 = c89.open_sftp()
        s93 = c93.open_sftp()
        size = s89.stat(REMOTE_TAR_89).st_size
        print(f"[xfer] {size} bytes", flush=True)
        transferred = 0
        t0 = time.time()
        with s89.open(REMOTE_TAR_89, "rb") as src, s93.open(REMOTE_TAR_93 + ".partial", "wb") as dst:
            while True:
                buf = src.read(4 * 1024 * 1024)
                if not buf:
                    break
                dst.write(buf)
                transferred += len(buf)
                if transferred % (32 * 1024 * 1024) < 4 * 1024 * 1024:
                    el = max(time.time() - t0, 0.1)
                    print(f"  … {transferred/1e6:.0f}/{size/1e6:.0f} MB ({transferred/el/1e6:.1f} MB/s)", flush=True)
        s89.close()
        s93.close()
        run(c93, f"mv -f {REMOTE_TAR_93}.partial {REMOTE_TAR_93} && ls -lh {REMOTE_TAR_93}")
    finally:
        c89.close()
        c93.close()


def phase_load_93() -> None:
    c = ssh(HOST93, PWD93)
    try:
        run(c, f"gunzip -c {REMOTE_TAR_93} | docker load", timeout=1200)
        run(c, "docker images --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}' | grep mlnocodb | head -20")
        run(
            c,
            "docker run --rm "
            + IMAGE
            + " node -e \"require('mssql');console.log('mssql_ok');"
            "var fs=require('fs');var t=fs.readFileSync('/usr/src/app/docker/main.js','utf8');"
            "console.log('MssqlClient',(t.match(/MssqlClient/g)||[]).length);\"",
            timeout=120,
        )
    finally:
        c.close()


def phase_cutover_93() -> None:
    c = ssh(HOST93, PWD93)
    try:
        run(c, "grep -nE 'image:|container_name|^  [a-z].*:|NC_DB|ports' /opt/mlnocodb/docker-compose.yml | head -50", check=False)

        # Patch only mlnocodb image tags; leave node/nginx alone
        run(
            c,
            "cd /opt/mlnocodb && "
            f"sed -i.bak.cutover 's#image: *mlnocodb:[^[:space:]]*#image: {IMAGE}#g; "
            f"s#image: *sha256:[a-f0-9]*#image: {IMAGE}#g' docker-compose.yml && "
            "grep -n 'image:' docker-compose.yml | head -20",
        )

        t0 = time.time()
        code, _, _ = run(
            c,
            "cd /opt/mlnocodb && "
            "(docker compose up -d --force-recreate --no-deps api "
            "|| docker compose up -d --force-recreate --no-deps mlnocodb-api "
            "|| docker-compose up -d --force-recreate --no-deps api "
            "|| docker-compose up -d --force-recreate --no-deps mlnocodb-api)",
            timeout=240,
            check=False,
        )
        if code != 0:
            print("compose recreate failed, trying stop/rm/up", flush=True)
            run(
                c,
                "cd /opt/mlnocodb && docker stop mlnocodb-api; docker rm mlnocodb-api; "
                "(docker compose up -d api || docker-compose up -d api || "
                "docker compose up -d mlnocodb-api || docker-compose up -d mlnocodb-api)",
                timeout=240,
            )
        print(f"[cutover] downtime_window≈{time.time()-t0:.1f}s", flush=True)

        ok = False
        last = ""
        for _ in range(40):
            _, last, _ = run(
                c,
                "curl -sf -m 5 http://127.0.0.1:6080/api/v1/health && echo HEALTH_OK; "
                "curl -s -m 5 http://127.0.0.1:6080/api/v1/version; echo",
                check=False,
            )
            if "HEALTH_OK" in last or "0.301" in last:
                ok = True
                break
            time.sleep(2)
        if not ok:
            raise RuntimeError(f"health failed: {last}")

        run(
            c,
            "echo VERSION; curl -s http://127.0.0.1:6080/api/v1/version; echo; "
            "echo HEALTH; curl -s http://127.0.0.1:6080/api/v1/health; echo; "
            "docker exec mlnocodb-api node -e \"require('mssql');console.log('mssql_ok')\"; "
            "docker exec mlnocodb-api sh -c 'grep -c MssqlClient /usr/src/app/docker/main.js'; "
            "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}'; "
            f"echo BACKUP_DIR={BACKUP_DIR}; ls -lh {BACKUP_DIR}/",
        )
        print(
            "\n=== ROLLBACK ===\n"
            f"cd /opt/mlnocodb\n"
            f"cp {BACKUP_DIR}/docker-compose.yml ./docker-compose.yml\n"
            f"# or: sed -i 's#image: mlnocodb:.*#image: mlnocodb:0.1.1-pre-{TAG}#' docker-compose.yml\n"
            f"docker compose up -d --force-recreate --no-deps api\n"
            f"# if image missing: gunzip -c {BACKUP_DIR}/mlnocodb-0.1.1-pre-{TAG}.tar.gz | docker load\n",
            flush=True,
        )
    finally:
        c.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase",
        choices=["all", "build", "backup", "xfer", "load", "cutover"],
        default="all",
    )
    args = ap.parse_args()
    phases = {
        "build": ("=== BUILD on 89 ===", phase_build_on_89),
        "backup": ("=== BACKUP on 93 (online) ===", phase_backup_93),
        "xfer": ("=== XFER tarball ===", phase_xfer),
        "load": ("=== LOAD image on 93 (online) ===", phase_load_93),
        "cutover": ("=== CUTOVER (brief downtime) ===", phase_cutover_93),
    }
    order = ["build", "backup", "xfer", "load", "cutover"] if args.phase == "all" else [args.phase]
    for name in order:
        title, fn = phases[name]
        print(title, flush=True)
        fn()
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAILED:", e, file=sys.stderr)
        raise
