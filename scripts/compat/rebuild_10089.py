#!/usr/bin/env python3
"""Diagnose build context on 100.89 and rebuild with full logs."""
import os
import sys
import time

import paramiko

sys.stdout.reconfigure(line_buffering=True)
HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")


def run(c, cmd, timeout=900):
    print(f"\n$ {cmd[:250]}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    print(out.rstrip()[:5000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(c, "ls -laR /opt/mlnocodb/build | head -80")
        run(c, "wc -c /opt/mlnocodb/build/docker/main.js; file /opt/mlnocodb/build/docker/main.js; head -c 80 /opt/mlnocodb/build/Dockerfile.centos; echo; cat /opt/mlnocodb/build/Dockerfile.centos")
        run(c, "find /opt/mlnocodb/build -type f | head -40")

        # Restore correct 0.301.2 tag if we overwrote it - list digests
        run(c, "docker images nocodb/nocodb --digests --format 'table {{.Tag}}\\t{{.ID}}\\t{{.Size}}'")

        # Rebuild with progress=plain to see real errors
        print("\n=== rebuild plain ===", flush=True)
        code, out = run(
            c,
            "cd /opt/mlnocodb/build && DOCKER_BUILDKIT=1 docker build --progress=plain --network=host "
            "-t mlnocodb:0.1.3 -f Dockerfile.centos . 2>&1 | tee /tmp/mlnoco-build.log | tail -80",
            timeout=900,
        )
        run(c, "tail -100 /tmp/mlnoco-build.log")
        if code != 0:
            # try without mssql if npm fails — create Dockerfile.lite
            print("\n=== try lite dockerfile without npm if needed ===", flush=True)
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
                "cd /opt/mlnocodb/build && docker build --progress=plain --network=host "
                "-t mlnocodb:0.1.3 -f Dockerfile.lite . 2>&1 | tee /tmp/mlnoco-build2.log | tail -100",
                timeout=900,
            )
            run(c, "tail -60 /tmp/mlnoco-build2.log")
            if code != 0:
                return 1

        run(c, "docker images mlnocodb")
        run(c, "docker run --rm mlnocodb:0.1.3 node -e \"require('mssql'); console.log('mssql_ok')\"")

        run(c, "docker rm -f mlnocodb-api mlnocodb-ui 2>/dev/null || true")
        run(c, "cd /opt/mlnocodb && docker compose up -d")
        time.sleep(28)
        run(c, "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'")
        run(c, "docker logs --tail 40 mlnocodb-api 2>&1")
        run(
            c,
            "curl -s -m 12 -X POST http://127.0.0.1:6080/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' -d '{\"email\":\"a@b.c\",\"password\":\"x\"}' | head -c 250; echo",
        )
        run(c, "curl -s -m 10 -o /dev/null -w 'UI=%{http_code}\\n' http://127.0.0.1:6100/")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
