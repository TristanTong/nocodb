#!/usr/bin/env python3
"""Confirm 93 nginx serves UI with MSSQL integration strings."""
from __future__ import annotations

import os
import re
import time

import paramiko

PWD = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("192.168.100.93", username="root", password=PWD, timeout=25)
    try:
        for i in range(15):
            _, o, _ = c.exec_command(
                "curl -sf -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1/; "
                "docker inspect -f '{{.State.Status}}' mlnocodb-ui; "
                "docker logs --tail 5 mlnocodb-ui 2>&1 | tail -5",
                timeout=30,
            )
            out = o.read().decode("utf-8", "replace")
            print(f"try{i}:", out[:300], flush=True)
            if out.startswith("200") and "running" in out:
                break
            time.sleep(2)

        cmd = r"""
HTML=$(curl -s http://127.0.0.1/)
echo "$HTML" | head -c 500; echo
ENTRY=$(echo "$HTML" | sed -n 's/.*href="\(_nuxt\/[^"]*\.js\)".*/\1/p' | head -1)
# also modulepreload
ENTRY2=$(echo "$HTML" | grep -oE '_nuxt/[^"]+\.js' | head -1)
echo ENTRY=$ENTRY ENTRY2=$ENTRY2
JS=${ENTRY:-$ENTRY2}
curl -s "http://127.0.0.1/$JS" -o /tmp/entry.js
wc -c /tmp/entry.js
# find chunk that has mssql i18n - fetch a few likely from entry imports is hard; scan disk served path
grep -Rql --include='*.js' 'objects.syncData.mssql' /opt/mlnocodb/ui/public/_nuxt && echo DISK_OK
# via nginx static? usually nitro serves
# pull one known file from 89-synced build
F=$(grep -Rl --include='*.js' 'objects.syncData.mssql' /opt/mlnocodb/ui/public/_nuxt | head -1)
BN=$(basename "$F")
echo fetch_via_nginx=$BN
curl -sf -m 10 "http://127.0.0.1/_nuxt/$BN" -o /tmp/mssqlchunk.js && grep -o 'objects.syncData.mssql' /tmp/mssqlchunk.js | head -1 && echo NGINX_MSSQL_OK
# also SQL Server string
grep -o 'SQL Server' /tmp/mssqlchunk.js | head -1 || true
docker ps --filter name=mlnocodb --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
"""
        _, o, e = c.exec_command(cmd, timeout=60)
        print(o.read().decode("utf-8", "replace"))
        err = e.read().decode("utf-8", "replace")
        if err.strip():
            print("ERR", err[-400:])
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
