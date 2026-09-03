#!/usr/bin/env python3
"""Upload local docker/main.js to 100.89 and recreate API with committed image."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")
REMOTE = "/opt/mlnocodb"
LOCAL = Path(__file__).resolve().parents[2] / "packages" / "nocodb" / "docker" / "main.js"


def run(c, cmd, timeout=300):
    print(f"\n$ {cmd[:280]}", flush=True)
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    clean = "".join(ch for ch in out if ord(ch) < 0x2800 or ord(ch) > 0x28FF)
    if clean.strip():
        print(clean.rstrip()[:4000], flush=True)
    print(f"exit={code}", flush=True)
    return code, clean


def main():
    if not LOCAL.is_file():
        raise SystemExit(f"missing {LOCAL}")
    text = LOCAL.read_text(encoding="utf-8", errors="replace")
    if "Primary key is required to delete records" not in text:
        raise SystemExit("local main.js missing PK delete guard — rebuild first")
    if "EREQUEST" not in text:
        raise SystemExit("local main.js missing EREQUEST handling")

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        remote_path = f"{REMOTE}/build/docker/main.js"
        run(c, f"mkdir -p {REMOTE}/build/docker")
        print(f"sftp put {LOCAL} -> {remote_path} ({LOCAL.stat().st_size} bytes)", flush=True)
        sftp = c.open_sftp()
        sftp.put(str(LOCAL), remote_path)
        sftp.close()
        run(
            c,
            f"grep -c MssqlClient {remote_path}; "
            f"grep -c 'Primary key is required to delete records' {remote_path}; "
            f"wc -c {remote_path}",
        )
        run(c, f"docker cp {remote_path} mlnocodb-api:/usr/src/app/docker/main.js")
        run(c, "docker commit mlnocodb-api mlnocodb:0.1.3")
        run(
            c,
            f"grep -n 'image:' {REMOTE}/docker-compose.yml | head -20; "
            f"sed -i 's#image: sha256:[a-f0-9]*#image: mlnocodb:0.1.3#' {REMOTE}/docker-compose.yml; "
            f"sed -i 's#image: mlnocodb:0.1.[0-9]*#image: mlnocodb:0.1.3#' {REMOTE}/docker-compose.yml; "
            f"grep -n 'image:' {REMOTE}/docker-compose.yml | head -20",
        )
        run(c, f"cd {REMOTE} && docker compose up -d --force-recreate api")
        time.sleep(25)
        run(
            c,
            "docker exec mlnocodb-api sh -c "
            "'echo MssqlClient=$(grep -c MssqlClient /usr/src/app/docker/main.js); "
            "echo pk_guard=$(grep -c \"Primary key is required to delete records\" /usr/src/app/docker/main.js); "
            "node -e \"require(\\\"mssql\\\");console.log(\\\"mssql_ok\\\")\"'; "
            "curl -s -m 10 http://127.0.0.1:8080/api/v1/health; echo; "
            "curl -s -m 10 http://127.0.0.1:8080/api/v1/version; echo'",
        )
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
