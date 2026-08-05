#!/usr/bin/env python3
"""Copy fixed main.js into running mlnocodb-api on 100.89 (mssql already installed)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")
LOCAL_MAIN = Path(r"D:\Project\nocodb\mlnocodb\packages\nocodb\docker\main.js")
REMOTE_TMP = "/tmp/mlnocodb-main-mssql-fix.js"


def run(c, cmd, timeout=120):
    print(f"\n$ {cmd[:300]}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip()[:4000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        sftp = c.open_sftp()
        print(f"Upload {LOCAL_MAIN} -> {REMOTE_TMP}", flush=True)
        sftp.put(str(LOCAL_MAIN), REMOTE_TMP)
        sftp.close()

        code, _ = run(
            c,
            "docker exec mlnocodb-api sh -c "
            "'node -e \"require(\\\"mssql\\\"); console.log(\\\"mssql_pkg_ok\\\")\" && "
            "grep -c MssqlClient /usr/src/app/docker/main.js || true'",
        )
        if code != 0:
            print("mssql package missing in container; need image rebuild", flush=True)
            return 1

        run(c, f"docker cp {REMOTE_TMP} mlnocodb-api:/usr/src/app/docker/main.js")
        run(
            c,
            "docker exec mlnocodb-api sh -c "
            "'wc -c /usr/src/app/docker/main.js; "
            "grep -c MssqlClient /usr/src/app/docker/main.js; "
            "grep -c \"\\\"mssql\\\"===e.client\" /usr/src/app/docker/main.js'",
        )
        run(c, "docker restart mlnocodb-api")
        time.sleep(18)
        run(
            c,
            "curl -s -m 10 http://127.0.0.1:6080/api/v1/health; echo; "
            "docker logs --tail 20 mlnocodb-api 2>&1; "
            "docker exec mlnocodb-api sh -c 'grep -c MssqlClient /usr/src/app/docker/main.js'",
        )

        # Also refresh build context + commit image so recreate keeps fix
        run(c, f"cp -f {REMOTE_TMP} /opt/mlnocodb/build/docker/main.js")
        run(
            c,
            "docker commit mlnocodb-api mlnocodb:0.1.3 && "
            "docker images mlnocodb:0.1.3 --format '{{.ID}} {{.CreatedSince}} {{.Size}}'",
        )
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
