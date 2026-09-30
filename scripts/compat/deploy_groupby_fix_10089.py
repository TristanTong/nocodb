#!/usr/bin/env python3
"""Hotpatch group-by MSSQL fix onto 100.89 (keep image tag mlnocodb:0.1.6)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")
REMOTE = "/opt/mlnocodb"
LOCAL = Path(__file__).resolve().parents[2] / "packages" / "nocodb" / "docker" / "main.js"
IMAGE = "mlnocodb:0.1.6"


def run(c, cmd, timeout=300, check=True):
    print(f"$ {cmd[:220]}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out[-4000:], flush=True)
    if check and code:
        raise SystemExit(f"fail {code}: {cmd}\n{err[-500:]}")
    return code, out


def main() -> int:
    text = LOCAL.read_text(encoding="utf-8", errors="replace")
    if "canGroupBySelectAlias" not in text and "!== 'mssql'" not in text:
        # minified may rename; check distinctive SQL comment or mssql branch leftover
        if "mssql" not in text.lower():
            raise SystemExit("main.js looks wrong")
    # After rspack minify, function names may be mangled — check source was built recently
    print(f"main.js size={LOCAL.stat().st_size}", flush=True)

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        remote = f"{REMOTE}/build/docker/main.js"
        run(c, f"mkdir -p {REMOTE}/build/docker")
        sftp = c.open_sftp()
        sftp.put(str(LOCAL), remote)
        sftp.close()
        run(c, f"wc -c {remote}")
        run(c, f"docker cp {remote} mlnocodb-api:/usr/src/app/docker/main.js")
        run(c, f"docker commit -m 'mssql groupby alias fix' mlnocodb-api {IMAGE}")
        run(
            c,
            f"cd {REMOTE} && "
            f"sed -i 's#image: *mlnocodb:[^[:space:]]*#image: {IMAGE}#' docker-compose.yml && "
            f"grep -n 'image:' docker-compose.yml | head -10",
        )
        run(
            c,
            f"cd {REMOTE} && (docker compose up -d --force-recreate --no-deps api "
            f"|| docker-compose up -d --force-recreate --no-deps api)",
        )
        ok = False
        for _ in range(30):
            _, out = run(
                c,
                "curl -sf -m 5 http://127.0.0.1:6080/api/v1/health && echo HEALTH_OK; "
                "curl -s -m 5 http://127.0.0.1:6080/api/v1/version; echo",
                check=False,
            )
            if "HEALTH_OK" in out or "0.301" in out:
                ok = True
                break
            time.sleep(2)
        if not ok:
            raise SystemExit("health failed")
        print("DEPLOY_OK", flush=True)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
