#!/usr/bin/env python3
"""Hot-fix docker/main.js on 100.89 and rebuild mlnocodb:0.1.3 (MSSQL fix)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")
LOCAL_MAIN = Path(r"D:\Project\nocodb\mlnocodb\packages\nocodb\docker\main.js")
REMOTE_MAIN = "/opt/mlnocodb/build/docker/main.js"
IMAGE = "mlnocodb:0.1.3"


def run(c, cmd, timeout=900):
    print(f"\n$ {cmd[:280]}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip()[:6000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def main():
    if not LOCAL_MAIN.exists():
        print("missing", LOCAL_MAIN)
        return 1
    size = LOCAL_MAIN.stat().st_size
    print(f"Local main.js {size} bytes", flush=True)

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        sftp = c.open_sftp()
        print(f"Upload -> {REMOTE_MAIN}", flush=True)
        sftp.put(str(LOCAL_MAIN), REMOTE_MAIN)
        sftp.close()

        run(
            c,
            f"wc -c {REMOTE_MAIN}; sha256sum {REMOTE_MAIN} | cut -c1-16; "
            f"grep -o '\"mssql\"===e.client' {REMOTE_MAIN} | wc -l; "
            f"grep -o MssqlClient {REMOTE_MAIN} | wc -l",
        )

        # Prefer existing Dockerfile.centos; fall back to lite overlay
        code, _ = run(
            c,
            "cd /opt/mlnocodb/build && DOCKER_BUILDKIT=1 docker build --network=host "
            f"-t {IMAGE} -f Dockerfile.centos . 2>&1 | tee /tmp/mlnoco-mssql-fix.log | tail -40",
            timeout=900,
        )
        if code != 0:
            run(c, "tail -80 /tmp/mlnoco-mssql-fix.log")
            lite = """FROM nocodb/nocodb:0.301.3
ENV NODE_ENV=production PORT=8080 NC_DOCKER=0.6 NC_TOOL_DIR=/usr/app/data/
COPY docker/main.js /usr/src/app/docker/main.js
COPY src/public/ /usr/src/app/docker/public/
RUN cd /usr/src/app && npm install mssql@11.0.1 --omit=dev --no-save --registry=https://registry.npmmirror.com && node -e "require('mssql'); console.log('mssql_ok')"
ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["node", "docker/main.js"]
"""
            sftp = c.open_sftp()
            with sftp.file("/opt/mlnocodb/build/Dockerfile.lite", "w") as f:
                f.write(lite)
            sftp.close()
            code, _ = run(
                c,
                "cd /opt/mlnocodb/build && docker build --network=host "
                f"-t {IMAGE} -f Dockerfile.lite . 2>&1 | tee /tmp/mlnoco-mssql-fix2.log | tail -50",
                timeout=900,
            )
            if code != 0:
                run(c, "tail -80 /tmp/mlnoco-mssql-fix2.log")
                return 1

        run(
            c,
            f"docker run --rm {IMAGE} sh -c "
            "'grep -o MssqlClient /usr/src/app/docker/main.js | wc -l; "
            "grep -o '\"mssql\"===e.client' /usr/src/app/docker/main.js | wc -l; "
            "node -e \"require(\\\"mssql\\\"); console.log(\\\"mssql_ok\\\")\"'",
        )

        run(c, "cd /opt/mlnocodb && docker compose up -d --force-recreate api")
        time.sleep(20)
        run(
            c,
            "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}'; "
            "curl -s -m 10 http://127.0.0.1:6080/api/v1/health; echo; "
            "docker logs --tail 25 mlnocodb-api 2>&1",
        )
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
