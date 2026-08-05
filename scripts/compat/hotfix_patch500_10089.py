#!/usr/bin/env python3
"""Hotfix remote NocoDB 0.301.3: only strip AI PK on INSERT (keep on UPDATE for PG batchUpdate)."""
from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from pathlib import Path

import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")
TOKEN = os.environ.get("NC_TOKEN", "")
REMOTE_HOST_PATH = "/tmp/nocodb-main.js"
CONTAINER = "mlnocodb-api"
CONTAINER_MAIN = "/usr/src/app/docker/main.js"

# Official minified prepareNocoData always strips AI pk when !undo (ignores isInsertData).
# Before: if(!(null==i?void 0:i.undo)){for(let t of this.model.primaryKeys)if(t.ai){
# After:  if(!(null==i?void 0:i.undo)&&t){for(let t of this.model.primaryKeys)if(t.ai){
# Here param `t` is isInsertData (still in scope before for-loop shadows it).
OLD = (
    "if(!(null==i?void 0:i.undo)){for(let t of this.model.primaryKeys)if(t.ai){"
    "let a=(null==e?void 0:e[t.column_name])!==void 0?t.column_name:t.title;"
    "void 0!==e[a]&&delete e[a]}}"
)
NEW = (
    "if(!(null==i?void 0:i.undo)&&t){for(let t of this.model.primaryKeys)if(t.ai){"
    "let a=(null==e?void 0:e[t.column_name])!==void 0?t.column_name:t.title;"
    "void 0!==e[a]&&delete e[a]}}"
)


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


def ssh_run(c: paramiko.SSHClient, cmd: str, timeout: int = 180) -> tuple[int, str]:
    print("$", cmd[:280], flush=True)
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip()[:2000], flush=True)
    print(" exit=", code, flush=True)
    return code, out


def main() -> int:
    local = Path(tempfile.gettempdir()) / "nocodb-main-10089.js"
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30, banner_timeout=60)

    print("BEFORE:6080", http_patch(f"http://{HOST}:6080", "热修前"), flush=True)

    # Prefer existing backup if present, else fresh copy
    ssh_run(
        c,
        f"docker cp {CONTAINER}:{CONTAINER_MAIN} {REMOTE_HOST_PATH} && "
        f"test -f {REMOTE_HOST_PATH}.bak-patch500 || "
        f"cp -a {REMOTE_HOST_PATH} {REMOTE_HOST_PATH}.bak-patch500",
    )

    sftp = c.open_sftp()
    sftp.get(REMOTE_HOST_PATH, str(local))
    sftp.close()

    s = local.read_text(encoding="utf-8", errors="ignore")
    cnt_old = s.count(OLD)
    cnt_new = s.count(NEW)
    print(f"OLD matches={cnt_old} NEW already={cnt_new}", flush=True)
    if cnt_old == 0 and cnt_new == 0:
        # show nearby snippet for debugging
        needle = "for(let t of this.model.primaryKeys)if(t.ai)"
        idx = s.find(needle)
        print("needle idx", idx, flush=True)
        if idx >= 0:
            print(s[idx - 80 : idx + 200], flush=True)
        c.close()
        return 2
    if cnt_old:
        s = s.replace(OLD, NEW)
        local.write_text(s, encoding="utf-8")
        print("patched", cnt_old, "occurrence(s)", flush=True)
    else:
        print("already patched, redeploying file", flush=True)

    sftp = c.open_sftp()
    sftp.put(str(local), REMOTE_HOST_PATH)
    sftp.close()

    ssh_run(c, f"docker cp {REMOTE_HOST_PATH} {CONTAINER}:{CONTAINER_MAIN}")
    ssh_run(c, f"docker restart {CONTAINER}")
    ssh_run(
        c,
        "sleep 12; docker ps --filter name=mlnocodb-api --format '{{.Status}}'; "
        "curl -s -o /dev/null -w 'health=%{http_code}\\n' http://127.0.0.1:6080/api/v1/health",
        timeout=90,
    )

    name6080 = "远程热修验证-API6080"
    name80 = "远程热修验证-nginx80"
    print("AFTER:6080", http_patch(f"http://{HOST}:6080", name6080), flush=True)
    print("GET:6080", http_get(f"http://{HOST}:6080"), flush=True)
    print("AFTER:80", http_patch(f"http://{HOST}", name80), flush=True)
    print("GET:80", http_get(f"http://{HOST}"), flush=True)

    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
