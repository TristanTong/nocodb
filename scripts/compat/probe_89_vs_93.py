#!/usr/bin/env python3
"""Probe deployment on 100.89 (test) and 100.93 (prod)."""
from __future__ import annotations

import hashlib
import json
import os
import sys

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

TARGETS = [
    {
        "name": "test-89",
        "host": "192.168.100.89",
        "pwd": os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd"),
        "user": "root",
    },
    {
        "name": "prod-93",
        "host": "192.168.100.93",
        "pwd": os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025"),
        "user": "root",
    },
]


def run(c, cmd, timeout=45):
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    return code, out


def probe(target):
    print(f"\n========== {target['name']} {target['host']} ==========", flush=True)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(target["host"], username=target["user"], password=target["pwd"], timeout=30)
    try:
        cmds = [
            "hostname; date; uptime",
            "docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' | head -40",
            "docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}\t{{.Size}}' | head -30",
            "ls -la /opt/mlnocodb 2>/dev/null; echo '---'; ls -la /opt/mlnocodb/build 2>/dev/null | head -20",
            "test -f /opt/mlnocodb/docker-compose.yml && echo HAS_COMPOSE || echo NO_COMPOSE; "
            "test -f /opt/mlnocodb/nginx.conf && echo HAS_NGINX || echo NO_NGINX",
            "grep -E 'image:|NC_|NUXT_|container_name|ports:' /opt/mlnocodb/docker-compose.yml 2>/dev/null | head -80",
            "docker inspect mlnocodb-api --format '{{.Image}} {{.Created}}' 2>/dev/null; "
            "docker inspect mlnocodb-api --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep -E 'NC_|PORT|TZ' | head -30",
            "docker inspect mlnocodb-ui --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep -E 'NUXT_|PORT|NITRO' | head -20",
            "wc -c /opt/mlnocodb/build/docker/main.js /usr/src/app/docker/main.js 2>/dev/null; "
            "docker exec mlnocodb-api sh -c 'wc -c /usr/src/app/docker/main.js; sha256sum /usr/src/app/docker/main.js | cut -c1-16; "
            "grep -c MssqlClient /usr/src/app/docker/main.js || true; "
            "grep -c \"\\\"mssql\\\"===e.client\" /usr/src/app/docker/main.js || true; "
            "node -e \"try{require(\\\"mssql\\\");console.log(\\\"mssql_pkg_ok\\\")}catch(e){console.log(\\\"mssql_pkg_missing\\\")}\"'",
            "curl -s -m 8 http://127.0.0.1/api/v1/health; echo; "
            "curl -s -m 8 http://127.0.0.1:6080/api/v1/health; echo; "
            "curl -s -m 8 -o /dev/null -w 'ui80=%{http_code}\\n' http://127.0.0.1/; "
            "curl -s -m 8 -o /dev/null -w 'ui6100=%{http_code}\\n' http://127.0.0.1:6100/",
            "docker exec mlnocodb-api sh -c "
            "'grep -oE \"ncBackendUrl:\\\"[^\"]+\\\"|ncBackendUrl:window.location.origin\" /usr/src/app/docker/main.js 2>/dev/null | head -3; true'",
            "curl -s -m 8 http://127.0.0.1/ | grep -oE 'ncBackendUrl[^,]{0,90}' | head -3",
            "docker exec postgres psql -U postgres -d mlnoco -c "
            "\"SELECT uidt, count(*) FROM nc_columns_v2 WHERE column_name='nc_order' GROUP BY uidt;\" 2>/dev/null || "
            "PGPASSWORD=Pass@w0rd psql -h 127.0.0.1 -U postgres -d mlnoco -c "
            "\"SELECT uidt, count(*) FROM nc_columns_v2 WHERE column_name='nc_order' GROUP BY uidt;\" 2>/dev/null || echo 'no_local_pg'",
            "grep -E 'proxy_pass|listen |location |sub_filter|Host' /opt/mlnocodb/nginx.conf 2>/dev/null | head -60",
        ]
        result = {"host": target["host"], "name": target["name"]}
        for cmd in cmds:
            code, out = run(c, cmd)
            print(f"\n$ {cmd[:200]}", flush=True)
            print(out.rstrip()[:4500], flush=True)
            print(f"exit={code}", flush=True)
        return result
    finally:
        c.close()


def main():
    for t in TARGETS:
        try:
            probe(t)
        except Exception as e:
            print(f"FAIL {t['host']}: {e}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
