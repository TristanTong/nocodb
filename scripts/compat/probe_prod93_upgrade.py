#!/usr/bin/env python3
"""Probe 100.93 production deploy state for upgrade risk assessment."""
from __future__ import annotations

import json
import os
import sys

import paramiko

HOST = "192.168.100.93"
PWD = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")


def run(c, cmd, timeout=60):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    return code, out, err


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=25)
    try:
        cmds = [
            "docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' | head -30",
            "cd /opt/mlnocodb && (test -f docker-compose.yml && grep -nE 'image:|NC_|volumes|ports' docker-compose.yml | head -80)",
            "docker images --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}} {{.CreatedSince}}' | grep -iE 'mlnocodb|nocodb|node|nginx' | head -30",
            "docker exec mlnocodb-api sh -c 'echo VER; curl -s -m 5 http://127.0.0.1:8080/api/v1/version; echo; echo MssqlClient=$(grep -c MssqlClient /usr/src/app/docker/main.js 2>/dev/null || echo 0); echo size=$(wc -c </usr/src/app/docker/main.js); node -e \"try{require(\\\"mssql\\\");console.log(\\\"mssql_ok\\\")}catch(e){console.log(\\\"mssql_missing\\\",e.code)}\"; printenv | grep -E \"^NC_|NODE_ENV\" | sed \"s/PASSWORD=.*/PASSWORD=***/;s/p=[^&]*/p=***/\" '",
            "docker exec mlnocodb-api sh -c 'ls -la /usr/src/app/docker/main.js; ls /usr/src/app/node_modules/mssql 2>/dev/null | head -3'",
            "df -h / /opt 2>/dev/null | head -10",
            "free -h | head -5",
            "ls -la /opt/mlnocodb/ | head -40",
            "test -f /opt/mlnocodb/docker-compose.yml.bak* && ls -lt /opt/mlnocodb/docker-compose.yml* | head -10 || ls -lt /opt/mlnocodb/*.yml* 2>/dev/null | head -10",
        ]
        for cmd in cmds:
            print("\n====", cmd[:120])
            code, out, err = run(c, cmd)
            print(out[-3500:] if out else "(empty)")
            if err.strip():
                print("ERR", err[-400:])
            print("exit", code)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
