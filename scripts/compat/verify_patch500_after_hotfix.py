#!/usr/bin/env python3
"""Wait for remote NocoDB after hotfix and verify PATCH on :6080 and :80."""
from __future__ import annotations

import json
import os
import time
import urllib.request

import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")
TOKEN = os.environ.get("NC_TOKEN", "")


def http_patch(base: str, name: str) -> str:
    req = urllib.request.Request(
        f"{base}/api/v2/tables/m0ixin184tfhckp/records",
        data=json.dumps([{"id": 36, "original_name": name}], ensure_ascii=False).encode(
            "utf-8"
        ),
        headers={
            "xc-token": TOKEN,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return f"OK {resp.status} {resp.read()[:220].decode()}"
    except Exception as e:
        body = b""
        if hasattr(e, "read"):
            try:
                body = e.read()
            except Exception:
                pass
        return f"ERR {e} body={body[:280]!r}"


def http_get(base: str) -> str:
    req = urllib.request.Request(
        f"{base}/api/v2/tables/m0ixin184tfhckp/records?where=(id,eq,36)",
        headers={"xc-token": TOKEN, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
        rows = data.get("list") or data.get("records") or []
        if not rows:
            return f"OK empty {data}"
        row = rows[0]
        return f"OK name={row.get('original_name')!r} id={row.get('id')}"


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30, banner_timeout=60)

    for i in range(20):
        _, o, _ = c.exec_command(
            "docker ps --filter name=mlnocodb-api --format '{{.Status}}'; "
            "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:6080/api/v1/health; echo; "
            "docker logs --tail 15 mlnocodb-api 2>&1 | tail -n 15",
            timeout=30,
            get_pty=True,
        )
        out = o.read().decode("utf-8", "replace")
        print(f"--- try {i} ---", flush=True)
        print(out[:1500], flush=True)
        if "health" in out.lower() or "\n200" in out or out.strip().endswith("200") or " 200\n" in out or out.count("\n200") or "200" in out.split("\n")[1:3]:
            # crude: look for curl code 200
            lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
            if any(ln == "200" for ln in lines) or any(ln.endswith("200") and len(ln) <= 10 for ln in lines):
                print("ready", flush=True)
                break
        time.sleep(5)
    else:
        print("NOT READY", flush=True)

    c.close()

    name6080 = "远程热修验证-API6080"
    name80 = "远程热修验证-nginx80"
    print("AFTER:6080", http_patch(f"http://{HOST}:6080", name6080), flush=True)
    print("GET:6080", http_get(f"http://{HOST}:6080"), flush=True)
    print("AFTER:80", http_patch(f"http://{HOST}", name80), flush=True)
    print("GET:80", http_get(f"http://{HOST}"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
