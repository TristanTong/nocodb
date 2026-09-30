#!/usr/bin/env python3
"""Build mlnocodb:0.1.6 on 89 by committing over mlnocodb:0.1.3 (already has mssql).

Avoids npm network during docker build.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")
MAIN = Path(__file__).resolve().parents[2] / "packages" / "nocodb" / "docker" / "main.js"
PUBLIC = Path(__file__).resolve().parents[2] / "packages" / "nocodb" / "src" / "public"
IMAGE = "mlnocodb:0.1.6"
BASE = "mlnocodb:0.1.3"
TAR = "/opt/mlnocodb/mlnocodb-0.1.6.tar.gz"
TMP = "mlnocodb-build-016"


def run(c, cmd, timeout=600, check=True):
    print("$", cmd[:240], flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out[-4000:], flush=True)
    if err.strip() and code:
        print("ERR", err[-1500:], flush=True)
    if check and code:
        raise SystemExit(f"fail {code}: {cmd}\n{err[-500:]}")
    return code, out


def main() -> int:
    text = MAIN.read_text(encoding="utf-8", errors="replace")
    for needle in ("MssqlClient", "Primary key is required to delete records", "EREQUEST"):
        if needle not in text:
            raise SystemExit(f"main.js missing {needle}")

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(c, f"docker rm -f {TMP} 2>/dev/null; docker create --name {TMP} {BASE}")
        sftp = c.open_sftp()
        remote_main = f"/tmp/{TMP}-main.js"
        sftp.put(str(MAIN), remote_main)
        print("uploaded main.js", MAIN.stat().st_size, flush=True)
        run(c, f"rm -rf /tmp/{TMP}-public && mkdir -p /tmp/{TMP}-public")
        for root, _dirs, files in os.walk(PUBLIC):
            rel = os.path.relpath(root, PUBLIC).replace("\\", "/")
            rdir = f"/tmp/{TMP}-public" if rel == "." else f"/tmp/{TMP}-public/{rel}"
            run(c, f"mkdir -p {rdir}", check=False)
            for fn in files:
                sftp.put(str(Path(root) / fn), f"{rdir}/{fn}")
        sftp.close()
        run(c, f"docker cp {remote_main} {TMP}:/usr/src/app/docker/main.js")
        run(c, f"docker cp /tmp/{TMP}-public/. {TMP}:/usr/src/app/docker/public/")
        run(c, f"docker commit -m 'v0.1.6 from {BASE}+main.js' {TMP} {IMAGE}")
        run(c, f"docker rm -f {TMP}")
        run(
            c,
            "docker run --rm "
            + IMAGE
            + " node -e \"require('mssql');console.log('mssql_ok');"
            "var fs=require('fs');var t=fs.readFileSync('/usr/src/app/docker/main.js','utf8');"
            "console.log('MssqlClient',(t.match(/MssqlClient/g)||[]).length);"
            "console.log('pk',t.includes('Primary key is required to delete records'));\"",
        )
        run(c, f"mkdir -p /opt/mlnocodb && docker save {IMAGE} | gzip -c > {TAR}", timeout=900)
        run(c, f"ls -lh {TAR}; docker images --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}' | grep mlnocodb | head -10")
        print("BUILD_OK", flush=True)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
