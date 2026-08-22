#!/usr/bin/env python3
"""Inspect 100.89 compose/nginx/env and how frontend resolves backend URL."""
from __future__ import annotations

import os
import sys

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")


def run(c, cmd, timeout=60):
    print(f"\n$ {cmd[:280]}", flush=True)
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    print(out.rstrip()[:7000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(c, "docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'")
        run(c, "echo '=== compose env ==='; grep -E 'NC_|NUXT_|image:|container' /opt/mlnocodb/docker-compose.yml")
        run(c, "echo '=== api env ==='; docker inspect mlnocodb-api --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'NC_|PORT|TZ'")
        run(c, "echo '=== ui env ==='; docker inspect mlnocodb-ui --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'NUXT_|PORT|NITRO'")
        run(c, "echo '=== nginx.conf ==='; cat /opt/mlnocodb/nginx.conf")
        run(
            c,
            "echo '=== baked backend url in UI ==='; "
            "grep -oE 'http://[^\"'\"'\"']{5,80}' /opt/mlnocodb/ui-output/public/_nuxt/*.js 2>/dev/null | grep -E '192.168|6080|6100|oa.medlinket|localhost' | sort | uniq | head -40; "
            "grep -Rlo 'ncBackendUrl' /opt/mlnocodb/ui-output --include='*.js' --include='*.mjs' 2>/dev/null | head -10",
        )
        run(
            c,
            "echo '=== nitro runtime config ==='; "
            "grep -n 'ncBackendUrl\\|NUXT_PUBLIC_NC_BACKEND' /opt/mlnocodb/ui-output/server/chunks/*.mjs 2>/dev/null | head -20; "
            "ls /opt/mlnocodb/ui-output | head",
        )
        run(
            c,
            "echo '=== local health via nginx ==='; "
            "curl -sI -m 8 http://127.0.0.1/ | head -15; echo; "
            "curl -s -m 8 http://127.0.0.1/api/v1/health; echo; "
            "curl -sI -m 8 -H 'Origin: http://oa.medlinket.com:19999' http://127.0.0.1/api/v1/health | head -20",
        )
        run(
            c,
            "echo '=== public domain from server ==='; "
            "curl -sI -m 10 http://oa.medlinket.com:19999/ | head -20; echo; "
            "curl -s -m 10 http://oa.medlinket.com:19999/api/v1/health; echo",
        )
        run(
            c,
            "echo '=== HTML script config ==='; "
            "curl -s -m 8 http://127.0.0.1/ | grep -oE 'ncBackendUrl[^<]{0,120}|http://192.168.100.89[^\"'\"'\"']*|NUXT[^<]{0,80}' | head -20",
        )
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
