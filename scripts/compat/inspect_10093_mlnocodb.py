#!/usr/bin/env python3
"""Inspect current mlnocodb containers on 100.93 and verify PG 100.97 meta DB."""
import os
import sys

import paramiko

HOST = "192.168.100.93"

CMDS = [
    ("current api env", "docker inspect mlnocodb-api --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'NC_DB|NC_PUBLIC_URL'"),
    ("current ui env", "docker inspect mlnocodb-ui --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'NUXT|PORT'"),
    ("images present", "docker images --format '{{.Repository}}:{{.Tag}} {{.Size}}' | grep -E '^(mlnocodb|node)' || echo MISSING"),
    ("ui files", "ls /opt/mlnocodb/ui/server/index.mjs /opt/mlnocodb/ui/nitro.json 2>&1; du -sh /opt/mlnocodb/ui"),
    ("pg databases on 100.97",
     "docker run --rm postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/postgres' -tAc \"select datname from pg_database where datname not in ('template0','template1')\""),
    ("mlnoco table count",
     "docker run --rm postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -tAc \"select count(*) from information_schema.tables where table_schema='public'\""),
    ("mlnoco nc tables sample",
     "docker run --rm postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -tAc \"select table_name from information_schema.tables where table_schema='public' and table_name like 'nc_%' order by 1 limit 15\""),
    ("mlnoco bases count",
     "docker run --rm postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -tAc \"select count(*) as bases from nc_sources_v2\" 2>&1 || true"),
    ("mlnoco users count",
     "docker run --rm postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -tAc \"select count(*) as users from nc_users_v2\" 2>&1 || true"),
]


def main():
    pwd = os.environ.get("REMOTE_SSH_PASSWORD", "")
    if not pwd:
        print("REMOTE_SSH_PASSWORD required", file=sys.stderr)
        return 2
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=pwd, timeout=30)
    try:
        for title, cmd in CMDS:
            print(f"\n=== {title}")
            _, o, e = c.exec_command(cmd, timeout=120)
            out = o.read().decode("utf-8", "replace")
            err = e.read().decode("utf-8", "replace")
            if out.strip():
                print(out.rstrip())
            if err.strip() and "level=warning" not in err:
                print(err.rstrip())
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
