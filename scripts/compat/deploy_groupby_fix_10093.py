#!/usr/bin/env python3
"""Deploy MSSQL groupby fix to 100.93 (minimal downtime, keep mlnocodb:0.1.6 tag)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

HOST = "192.168.100.93"
PWD = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")
REMOTE = "/opt/mlnocodb"
LOCAL = Path(__file__).resolve().parents[2] / "packages" / "nocodb" / "docker" / "main.js"
IMAGE = "mlnocodb:0.1.6"
BACKUP_TAG = "mlnocodb:0.1.6-pre-groupby-fix"


def run(c, cmd, timeout=300, check=True):
    print(f"$ {cmd[:240]}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out[-4000:], flush=True)
    if check and code:
        raise SystemExit(f"fail {code}: {cmd}\n{err[-600:]}")
    return code, out


def main() -> int:
    if not LOCAL.is_file():
        raise SystemExit(f"missing {LOCAL}")
    size = LOCAL.stat().st_size
    print(f"main.js size={size}", flush=True)

    # Source-side sanity (minified bundle may not keep symbol names)
    src = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "nocodb"
        / "src"
        / "db"
        / "BaseModelSqlv2"
        / "group-by.ts"
    )
    st = src.read_text(encoding="utf-8")
    if "canGroupBySelectAlias" not in st or "rejects nested WITH" not in st:
        raise SystemExit("source group-by.ts missing MSSQL fix — rebuild first")

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(c, "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}'")
        run(c, "curl -s -m 5 http://127.0.0.1:6080/api/v1/version; echo")

        # Online: tag current running image for rollback
        run(
            c,
            f"ID=$(docker inspect -f '{{{{.Image}}}}' mlnocodb-api); "
            f"echo running=$ID; docker tag \"$ID\" {BACKUP_TAG}; "
            f"docker images --format '{{{{.Repository}}}}:{{{{.Tag}}}} {{{{.ID}}}}' | grep mlnocodb | head -10",
        )

        remote = f"{REMOTE}/build/docker/main.js"
        run(c, f"mkdir -p {REMOTE}/build/docker")
        print(f"put {LOCAL} -> {remote}", flush=True)
        sftp = c.open_sftp()
        sftp.put(str(LOCAL), remote)
        sftp.close()
        run(c, f"wc -c {remote}")

        # Brief downtime: cp + commit + recreate api only
        t0 = time.time()
        run(c, f"docker cp {remote} mlnocodb-api:/usr/src/app/docker/main.js")
        run(c, f"docker commit -m 'mssql groupby fix (alias+nested CTE)' mlnocodb-api {IMAGE}")
        run(
            c,
            f"cd {REMOTE} && "
            f"cp -a docker-compose.yml docker-compose.yml.bak.groupby-$(date +%Y%m%d%H%M%S) && "
            f"sed -i 's#image: *mlnocodb:[^[:space:]]*#image: {IMAGE}#' docker-compose.yml && "
            f"grep -n 'image:' docker-compose.yml | head -10",
        )
        run(
            c,
            f"cd {REMOTE} && (docker compose up -d --force-recreate --no-deps api "
            f"|| docker-compose up -d --force-recreate --no-deps api)",
        )
        print(f"[cutover]≈{time.time()-t0:.1f}s", flush=True)

        ok = False
        for _ in range(40):
            _, out = run(
                c,
                "curl -sf -m 5 http://127.0.0.1:6080/api/v1/health && echo HEALTH_OK; "
                "curl -s -m 5 http://127.0.0.1:6080/api/v1/version; echo; "
                "docker exec mlnocodb-api node -e \"require('mssql');console.log('mssql_ok')\"",
                check=False,
            )
            if "HEALTH_OK" in out and "mssql_ok" in out:
                ok = True
                break
            time.sleep(2)
        if not ok:
            raise SystemExit("health/mssql failed after deploy")

        run(
            c,
            "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}'; "
            f"echo ROLLBACK_TAG={BACKUP_TAG}",
        )
        print(
            "\nROLLBACK:\n"
            f"  cd {REMOTE}\n"
            f"  sed -i 's#image: mlnocodb:.*#image: {BACKUP_TAG}#' docker-compose.yml\n"
            "  docker compose up -d --force-recreate --no-deps api\n",
            flush=True,
        )
        print("DEPLOY_93_OK", flush=True)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
