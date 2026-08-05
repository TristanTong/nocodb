#!/usr/bin/env python3
"""Redeploy mlnocodb on 192.168.100.93 with PG at 192.168.100.97.

Only IPs changed; images and /opt/mlnocodb layout already exist on target.
Steps: show old env -> stop/rm containers -> write docker-compose.yml -> up -d -> verify.
"""
import os
import sys
import time

import paramiko

HOST = "192.168.100.93"

COMPOSE = """services:
  api:
    image: mlnocodb:0.1.1
    container_name: mlnocodb-api
    restart: always
    ports:
      - "6080:8080"
    environment:
      NC_DB: "pg://192.168.100.97:5432?u=postgres&p=Pass%40w0rd&d=mlnoco"
      NC_DISABLE_TELE: "true"
      NC_PUBLIC_URL: "http://192.168.100.93:6080"
      TZ: Asia/Shanghai
    volumes:
      - /opt/mlnocodb/data:/usr/app/data

  ui:
    image: node:22-slim
    container_name: mlnocodb-ui
    restart: always
    working_dir: /app
    command: ["node", "server/index.mjs"]
    ports:
      - "80:6100"
    environment:
      PORT: "6100"
      NUXT_PUBLIC_NC_BACKEND_URL: "http://192.168.100.93:6080"
      NUXT_PAGE_TRANSITION_DISABLE: "true"
      TZ: Asia/Shanghai
      NITRO_HOST: "0.0.0.0"
      NITRO_PORT: "6100"
    volumes:
      - /opt/mlnocodb/ui:/app:ro
"""


def run(c, cmd, timeout=300, show=True):
    if show:
        print(f"$ {cmd}")
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if show and out.strip():
        print(out.rstrip())
    if code != 0 and err.strip():
        print(err.rstrip(), file=sys.stderr)
    return code, out, err


def main():
    pwd = os.environ.get("REMOTE_SSH_PASSWORD", "")
    if not pwd:
        print("REMOTE_SSH_PASSWORD required", file=sys.stderr)
        return 2
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=pwd, timeout=30)
    try:
        print("=== old api env (before)")
        run(c, "docker inspect mlnocodb-api --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep -E 'NC_DB|NC_PUBLIC_URL' || echo NO_CONTAINER")

        print("\n=== write new docker-compose.yml")
        sftp = c.open_sftp()
        with sftp.file("/opt/mlnocodb/docker-compose.yml", "w") as f:
            f.write(COMPOSE)
        sftp.close()
        run(c, "cat /opt/mlnocodb/docker-compose.yml | grep -E 'NC_DB|NC_PUBLIC_URL|NUXT_PUBLIC'")

        print("\n=== stop & remove old containers")
        run(c, "docker rm -f mlnocodb-api mlnocodb-ui 2>&1 || true")

        print("\n=== compose up")
        code, out, err = run(c, "cd /opt/mlnocodb && docker compose up -d", timeout=300)
        if code != 0:
            print("compose up failed", file=sys.stderr)
            return 1

        print("\n=== wait for api boot")
        time.sleep(25)
        run(c, "docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}' | grep -E 'NAMES|mlnocodb'")

        print("\n=== api logs (tail)")
        run(c, "docker logs --tail 25 mlnocodb-api 2>&1")

        print("\n=== health checks")
        run(c, "curl -s -m 10 http://localhost:6080/api/v1/health || echo API_HEALTH_FAIL")
        run(c, "echo; curl -s -m 10 -o /dev/null -w 'API http_code=%{http_code}\\n' http://localhost:6080/")
        run(c, "curl -s -m 10 -o /dev/null -w 'UI  http_code=%{http_code}\\n' http://localhost:80/")

        print("\n=== ui logs (tail)")
        run(c, "docker logs --tail 8 mlnocodb-ui 2>&1")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
