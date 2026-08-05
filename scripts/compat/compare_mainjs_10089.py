#!/usr/bin/env python3
"""Compare main.js hash/mssql presence: local upload vs container on 100.89."""
import hashlib
import os
import sys
import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")


def run(c, cmd, timeout=60):
    print(f"$ {cmd}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    print(out.encode("ascii", "replace").decode().rstrip()[:2000], flush=True)
    return out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(
            c,
            "docker exec mlnocodb-api sh -c '"
            "wc -c /usr/src/app/docker/main.js; "
            "sha256sum /usr/src/app/docker/main.js | cut -c1-16; "
            "grep -o mssql /usr/src/app/docker/main.js | wc -l; "
            "grep -o \"client===.mssql.\" /usr/src/app/docker/main.js | head -3; "
            "grep -o \"Database .* is not supported\" /usr/src/app/docker/main.js | head -2"
            "'",
        )
        run(
            c,
            "wc -c /opt/mlnocodb/build/docker/main.js; "
            "sha256sum /opt/mlnocodb/build/docker/main.js | cut -c1-16; "
            "grep -o mssql /opt/mlnocodb/build/docker/main.js | wc -l",
        )
        # Does UI expose mssql in integrations list from appInfo?
        run(
            c,
            "curl -s -m 8 http://127.0.0.1:6080/api/v1/health; echo; "
            "curl -s -m 8 http://127.0.0.1/api/v1/health; echo",
        )
    finally:
        c.close()


if __name__ == "__main__":
    main()
