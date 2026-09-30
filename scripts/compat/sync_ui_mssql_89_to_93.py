#!/usr/bin/env python3
"""Sync nc-gui from 89 → 93 so Integrations page shows SQL Server.

Online: tar UI on 89, scp to 93, backup old /opt/mlnocodb/ui, swap in place.
Brief: recreate mlnocodb-ui only (nginx stays up; ~few seconds for UI).
"""
from __future__ import annotations

import os
import time

import paramiko

HOST89 = "192.168.100.89"
HOST93 = "192.168.100.93"
PWD89 = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")
PWD93 = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")

SRC = "/opt/mlnocodb/ui-output"
DST = "/opt/mlnocodb/ui"
TAR89 = "/tmp/nc-gui-ui-0.1.6.tgz"
TAR93 = "/opt/mlnocodb/nc-gui-ui-0.1.6.tgz"
BACKUP = "/opt/mlnocodb/backup-pre-0.1.6/ui-pre-0.1.6.tgz"


def ssh(host, pwd):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username="root", password=pwd, timeout=30)
    return c


def run(c, cmd, timeout=600, check=True):
    print("$", cmd[:220], flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out[-5000:], flush=True)
    if check and code:
        raise SystemExit(f"fail {code}: {cmd}\n{err[-800:]}\n{out[-400:]}")
    return code, out, err


def main() -> int:
    # 1) Confirm 89 has mssql marker, pack
    c89 = ssh(HOST89, PWD89)
    try:
        run(
            c89,
            f"grep -Rql --include='*.js' 'objects.syncData.mssql' {SRC}/public/_nuxt "
            f"&& echo MSSQL_UI_OK || (echo MSSQL_UI_MISSING; exit 2)",
        )
        run(c89, f"tar -czf {TAR89} -C {SRC} . && ls -lh {TAR89}", timeout=300)
    finally:
        c89.close()

    # 2) Pull to 93 via sshpass (LAN)
    c93 = ssh(HOST93, PWD93)
    try:
        run(
            c93,
            f"sshpass -p '{PWD89}' scp -o StrictHostKeyChecking=no "
            f"root@{HOST89}:{TAR89} {TAR93} && ls -lh {TAR93}",
            timeout=600,
        )

        # backup current UI (online)
        run(c93, f"mkdir -p /opt/mlnocodb/backup-pre-0.1.6")
        run(
            c93,
            f"if [ ! -s {BACKUP} ]; then tar -czf {BACKUP} -C {DST} .; fi; ls -lh {BACKUP}",
            timeout=300,
        )

        # stage new UI next to old
        run(c93, "rm -rf /opt/mlnocodb/ui.new && mkdir -p /opt/mlnocodb/ui.new")
        run(c93, f"tar -xzf {TAR93} -C /opt/mlnocodb/ui.new", timeout=300)
        run(
            c93,
            "grep -Rql --include='*.js' 'objects.syncData.mssql' /opt/mlnocodb/ui.new/public/_nuxt "
            "&& echo STAGED_MSSQL_OK || (echo STAGED_MSSQL_MISSING; exit 2)",
        )

        # atomic-ish swap + recreate UI only
        t0 = time.time()
        run(
            c93,
            f"rm -rf {DST}.old; mv {DST} {DST}.old; mv /opt/mlnocodb/ui.new {DST}",
        )
        run(
            c93,
            "cd /opt/mlnocodb && "
            "(docker compose up -d --force-recreate --no-deps ui "
            "|| docker-compose up -d --force-recreate --no-deps ui)",
            timeout=120,
        )
        print(f"[ui] swap+recreate≈{time.time()-t0:.1f}s", flush=True)

        # verify
        for _ in range(20):
            code, out, _ = run(
                c93,
                "curl -sf -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:6100/ || echo FAIL; "
                "curl -sf -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1/ || echo FAIL",
                check=False,
            )
            if "200" in out:
                break
            time.sleep(2)

        run(
            c93,
            f"grep -Rql --include='*.js' 'objects.syncData.mssql' {DST}/public/_nuxt && echo LIVE_MSSQL_OK; "
            f"cat {DST}/nitro.json; "
            "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}'",
        )
        print(
            "\nUI rollback:\n"
            f"  cd /opt/mlnocodb && rm -rf ui && mv ui.old ui\n"
            f"  # or: tar -xzf {BACKUP} -C {DST}\n"
            "  docker compose up -d --force-recreate --no-deps ui\n",
            flush=True,
        )
    finally:
        c93.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
