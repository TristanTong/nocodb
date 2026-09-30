#!/usr/bin/env python3
"""Post-upgrade verify on 100.93."""
from __future__ import annotations

import os
import paramiko

PWD = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")

CMD = r"""
docker exec mlnocodb-api sh -c '
echo MssqlClient=$(grep -o MssqlClient /usr/src/app/docker/main.js | wc -l)
echo pk=$(grep -c "Primary key is required to delete records" /usr/src/app/docker/main.js)
echo EREQUEST=$(grep -c EREQUEST /usr/src/app/docker/main.js)
echo applyMissingPk=$(grep -c applyMissingPkFallback /usr/src/app/docker/main.js)
wc -c /usr/src/app/docker/main.js
node -e "require(\"mssql\");console.log(\"mssql_ok\")"
'
echo VERSION=$(curl -s http://127.0.0.1:6080/api/v1/version)
echo HEALTH=$(curl -s http://127.0.0.1:6080/api/v1/health)
free -h | head -3
ls -lh /opt/mlnocodb/backup-pre-0.1.6/ /opt/mlnocodb/mlnocodb-0.1.6.tar.gz
grep -n image: /opt/mlnocodb/docker-compose.yml
docker ps --filter name=mlnocodb --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("192.168.100.93", username="root", password=PWD, timeout=25)
    try:
        _, o, e = c.exec_command(CMD, timeout=60)
        print(o.read().decode("utf-8", "replace"))
        err = e.read().decode("utf-8", "replace")
        if err.strip():
            print("STDERR", err[-500:])
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
