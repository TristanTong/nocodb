#!/usr/bin/env python3
"""Check whether deployed UI bundles mention MSSQL / SQL Server."""
from __future__ import annotations

import os
import paramiko

PWD89 = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")
PWD93 = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")


def check(host, pwd, label):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username="root", password=pwd, timeout=25)
    try:
        cmd = r"""
set -e
echo "=== """ + label + r""" ==="
# compose / mounts
cd /opt/mlnocodb && grep -nE 'ui|image:|volumes|6100|80:' docker-compose.yml | head -40
echo "--- nginx ---"
ls /opt/mlnocodb/nginx* 2>/dev/null | head -10
find /opt/mlnocodb -maxdepth 2 -type d -name 'ui*' 2>/dev/null
echo "--- UI dirs ---"
for d in /opt/mlnocodb/ui /opt/mlnocodb/ui-output; do
  if [ -d "$d" ]; then
    echo "DIR $d"
    du -sh "$d" 2>/dev/null
    # search built assets for mssql / SQL Server
    echo -n "mssql hits: "
    grep -Ril --include='*.js' --include='*.mjs' -e 'mssql' -e 'SQL Server' -e 'ClientType.MSSQL' -e '"mssql"' "$d" 2>/dev/null | head -5 | wc -l
    echo -n "sample files: "
    grep -Ril --include='*.js' --include='*.mjs' -e 'objects.syncData.mssql' -e 'mssqlServer' "$d" 2>/dev/null | head -3
    ls -la "$d" | head -15
  else
    echo "MISSING $d"
  fi
done
# also check if API embeds old dashboard
docker exec mlnocodb-api sh -c 'ls /usr/src/app/docker/public 2>/dev/null | head; grep -Ril mssql /usr/src/app/docker/public 2>/dev/null | head -3 || true'
"""
        _, o, e = c.exec_command(cmd, timeout=180)
        print(o.read().decode("utf-8", "replace"))
        err = e.read().decode("utf-8", "replace")
        if err.strip():
            print("ERR", err[-800:])
    finally:
        c.close()


def main():
    check("192.168.100.93", PWD93, "93-prod")
    check("192.168.100.89", PWD89, "89-test")


if __name__ == "__main__":
    main()
