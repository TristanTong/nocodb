#!/usr/bin/env python3
"""Fix 100.89 so login works via http://oa.medlinket.com:19999 (Chrome + off-LAN).

Root cause: UI baked NUXT_PUBLIC_NC_BACKEND_URL=http://192.168.100.89
so the browser calls the private IP instead of the mapped public origin.
"""
from __future__ import annotations

import os
import sys
import time

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")
REMOTE = "/opt/mlnocodb"

NGINX = r"""worker_processes auto;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;
    keepalive_timeout 65;
    client_max_body_size 100M;
    gzip off;

    map $http_upgrade $connection_upgrade {
        default upgrade;
        '' close;
    }

    server {
        listen 80;
        server_name _;

        location /api/ {
            proxy_pass http://api:8080;
            proxy_http_version 1.1;
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
            proxy_send_timeout 300s;
            client_max_body_size 100M;
        }

        location /jobs/ {
            proxy_pass http://api:8080;
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 120s;
            proxy_send_timeout 120s;
        }

        location /download/ {
            proxy_pass http://api:8080;
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
        }

        location /dl/ {
            proxy_pass http://api:8080;
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
        }

        location /dltemp/ {
            proxy_pass http://api:8080;
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
        }

        location /socket.io/ {
            proxy_pass http://api:8080;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_read_timeout 3600s;
        }

        location / {
            proxy_pass http://ui:6100;
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Accept-Encoding "";
            proxy_hide_header Content-Encoding;
            sub_filter_types text/html;
            sub_filter_once off;
            sub_filter 'ncBackendUrl:"http://192.168.100.89"' 'ncBackendUrl:window.location.origin';
            sub_filter 'ncBackendUrl:"http://oa.medlinket.com:19999"' 'ncBackendUrl:window.location.origin';
        }
    }
}
"""

COMPOSE = f"""services:
  nginx:
    image: nginx:alpine
    container_name: mlnocodb-nginx
    restart: always
    ports:
      - "80:80"
    volumes:
      - {REMOTE}/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - api
      - ui
    security_opt:
      - seccomp:unconfined

  api:
    image: mlnocodb:0.1.3
    container_name: mlnocodb-api
    restart: always
    ports:
      - "6080:8080"
    environment:
      NC_DB: "pg://192.168.100.89:5432?u=postgres&p=Pass%40w0rd&d=mlnoco"
      NC_DISABLE_TELE: "true"
      NC_PUBLIC_URL: "http://oa.medlinket.com:19999"
      TZ: Asia/Shanghai
    volumes:
      - {REMOTE}/data:/usr/app/data
    extra_hosts:
      - "host.docker.internal:host-gateway"

  ui:
    image: node:22-slim
    container_name: mlnocodb-ui
    restart: always
    working_dir: /app
    command: ["node", "server/index.mjs"]
    expose:
      - "6100"
    environment:
      PORT: "6100"
      NITRO_HOST: "0.0.0.0"
      NITRO_PORT: "6100"
      NUXT_PUBLIC_NC_BACKEND_URL: "http://oa.medlinket.com:19999"
      NUXT_PAGE_TRANSITION_DISABLE: "true"
      TZ: Asia/Shanghai
    volumes:
      - {REMOTE}/ui-output:/app:ro
"""


def run(c, cmd, timeout=180):
    print(f"\n$ {cmd[:280]}", flush=True)
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip()[:5000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(c, f"cp -a {REMOTE}/docker-compose.yml {REMOTE}/docker-compose.yml.bak.sameorigin.$(date +%Y%m%d%H%M%S)")
        run(c, f"cp -a {REMOTE}/nginx.conf {REMOTE}/nginx.conf.bak.sameorigin.$(date +%Y%m%d%H%M%S)")

        sftp = c.open_sftp()
        with sftp.file(f"{REMOTE}/nginx.conf", "w") as f:
            f.write(NGINX)
        with sftp.file(f"{REMOTE}/docker-compose.yml", "w") as f:
            f.write(COMPOSE)
        sftp.close()

        # Keep the currently running API image so recreate does not roll back MSSQL hotfix
        run(
            c,
            "IMG=$(docker inspect mlnocodb-api --format '{{.Image}}'); "
            "echo CURRENT_API_IMAGE=$IMG; "
            f"sed -i \"s#image: mlnocodb:0.1.3#image: $IMG#\" {REMOTE}/docker-compose.yml; "
            f"grep -n 'image:' {REMOTE}/docker-compose.yml",
        )

        # Recreate only app containers; keep existing image IDs
        code, _ = run(c, f"cd {REMOTE} && docker compose up -d --force-recreate api ui nginx")
        if code != 0:
            return 1

        time.sleep(18)
        run(c, "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'")
        run(c, "docker inspect mlnocodb-ui --format '{{range .Config.Env}}{{println .}}{{end}}' | grep NUXT_PUBLIC")
        run(c, "docker inspect mlnocodb-api --format '{{range .Config.Env}}{{println .}}{{end}}' | grep NC_PUBLIC")

        print("\n=== verify HTML backend url ===", flush=True)
        run(
            c,
            "curl -s -m 10 -H 'Host: oa.medlinket.com:19999' http://127.0.0.1/ "
            "| grep -oE 'ncBackendUrl[^,]{0,80}'",
        )
        run(
            c,
            "curl -s -m 10 -H 'Host: 192.168.100.89' http://127.0.0.1/ "
            "| grep -oE 'ncBackendUrl[^,]{0,80}'",
        )

        print("\n=== verify API via mapped Host ===", flush=True)
        run(c, "curl -s -m 8 -H 'Host: oa.medlinket.com:19999' http://127.0.0.1/api/v1/health; echo")
        run(
            c,
            "curl -s -m 10 -o /dev/null -w 'signin=%{http_code}\\n' "
            "-X POST http://127.0.0.1/api/v1/auth/user/signin "
            "-H 'Host: oa.medlinket.com:19999' "
            "-H 'Origin: http://oa.medlinket.com:19999' "
            "-H 'Content-Type: application/json' "
            "-d '{\"email\":\"a@b.c\",\"password\":\"x\"}'",
        )
        run(c, "curl -s -m 8 -o /dev/null -w 'ui=%{http_code}\\n' http://127.0.0.1/")
        run(c, "docker logs --tail 15 mlnocodb-nginx 2>&1")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
