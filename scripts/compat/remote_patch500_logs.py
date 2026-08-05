#!/usr/bin/env python3
"""Get real PATCH error from remote NocoDB logs / temp NODE_ENV."""
from __future__ import annotations

import json
import os
import urllib.request

import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")
TOKEN = os.environ.get("NC_TOKEN", "")


def http_patch() -> str:
    req = urllib.request.Request(
        f"http://{HOST}:6080/api/v2/tables/m0ixin184tfhckp/records",
        data=json.dumps([{"id": 36, "original_name": "远程调试名"}], ensure_ascii=False).encode("utf-8"),
        headers={
            "xc-token": TOKEN,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return f"OK {resp.status} {resp.read()[:300]}"
    except Exception as e:
        body = getattr(e, "read", lambda: b"")()
        return f"ERR {e} body={body[:500]!r}"


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30, banner_timeout=60)

    def run(cmd: str, timeout: int = 60) -> str:
        print("$", cmd[:200], flush=True)
        _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
        out = o.read().decode("utf-8", "replace")
        print(out.rstrip()[:3000], flush=True)
        return out

    run("docker logs --tail 5 mlnocodb-api 2>&1")
    print("PATCH...", flush=True)
    print(http_patch(), flush=True)
    run("docker logs --tail 80 mlnocodb-api 2>&1 | tail -80")

    # Search upstream-like patterns for prepareNocoData AI in 0.301.3 bundle
    run(
        "docker exec mlnocodb-api sh -c \"grep -o 'isInsertData.{0,40}undo.{0,80}' /usr/src/app/docker/main.js | head -5; "
        "grep -o 'primaryKeys.{0,120}ai.{0,120}' /usr/src/app/docker/main.js | head -5\""
    )

    # nginx container config
    run("docker exec mlnocodb-nginx sh -c 'cat /etc/nginx/conf.d/*.conf 2>/dev/null; cat /etc/nginx/nginx.conf' | head -80")

    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
