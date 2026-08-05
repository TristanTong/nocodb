#!/usr/bin/env python3
"""Add nginx:80 reverse proxy on 192.168.100.89 and point UI/API public URLs to :80."""
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
pid /tmp/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;
    keepalive_timeout 65;
    client_max_body_size 100M;

    map $http_upgrade $connection_upgrade {
        default upgrade;
        '' close;
    }

    server {
        listen 80;
        server_name _;

        location /api/ {
            proxy_pass http://api:8080;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
            proxy_send_timeout 300s;
            client_max_body_size 100M;
        }

        location /jobs/ {
            proxy_pass http://api:8080;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 120s;
            proxy_send_timeout 120s;
        }

        location /download/ {
            proxy_pass http://api:8080;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
        }

        location /dl/ {
            proxy_pass http://api:8080;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
        }

        location /dltemp/ {
            proxy_pass http://api:8080;
            proxy_set_header Host $host;
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
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_read_timeout 3600s;
        }

        location / {
            proxy_pass http://ui:6100;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
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

  api:
    image: mlnocodb:0.1.3
    container_name: mlnocodb-api
    restart: always
    ports:
      - "6080:8080"
    environment:
      NC_DB: "pg://192.168.100.89:5432?u=postgres&p=Pass%40w0rd&d=mlnoco"
      NC_DISABLE_TELE: "true"
      NC_PUBLIC_URL: "http://192.168.100.89"
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
    # no host publish for 6100 — access via nginx:80
    expose:
      - "6100"
    environment:
      PORT: "6100"
      NITRO_HOST: "0.0.0.0"
      NITRO_PORT: "6100"
      NUXT_PUBLIC_NC_BACKEND_URL: "http://192.168.100.89"
      NUXT_PAGE_TRANSITION_DISABLE: "true"
      TZ: Asia/Shanghai
    volumes:
      - {REMOTE}/ui-output:/app:ro
"""


def run(c, cmd, timeout=180):
    print(f"$ {cmd}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    print(out.encode("ascii", "replace").decode().rstrip()[:2500], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        # ensure nginx image
        code, out = run(c, "docker images -q nginx:alpine")
        if not out.strip():
            run(
                c,
                "docker pull nginx:alpine 2>&1 || "
                "(docker pull docker.m.daocloud.io/library/nginx:alpine && "
                "docker tag docker.m.daocloud.io/library/nginx:alpine nginx:alpine)",
                timeout=600,
            )

        sftp = c.open_sftp()
        with sftp.file(f"{REMOTE}/nginx.conf", "w") as f:
            f.write(NGINX)
        with sftp.file(f"{REMOTE}/docker-compose.yml", "w") as f:
            f.write(COMPOSE)
        sftp.close()

        run(c, f"cp -a {REMOTE}/docker-compose.yml {REMOTE}/docker-compose.yml.bak.$(date +%Y%m%d%H%M%S)")

        # recreate stack so env URLs update
        run(c, f"cd {REMOTE} && docker compose down 2>&1 || true")
        code, _ = run(c, f"cd {REMOTE} && docker compose up -d 2>&1")
        if code != 0:
            return 1

        time.sleep(8)
        run(c, "docker exec mlnocodb-nginx nginx -t && docker exec mlnocodb-nginx nginx -s reload")
        time.sleep(20)

        run(c, "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'")
        run(c, "docker inspect mlnocodb-api --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'NC_DB|NC_PUBLIC'")
        run(c, "docker inspect mlnocodb-ui --format '{{range .Config.Env}}{{println .}}{{end}}' | grep NUXT_PUBLIC")

        print("\n=== health via :80 ===", flush=True)
        run(c, "curl -s -m 10 -o /dev/null -w 'UI=%{http_code}\\n' http://127.0.0.1/")
        run(
            c,
            "curl -s -m 10 -X POST http://127.0.0.1/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' -d '{\"email\":\"a@b.c\",\"password\":\"x\"}'",
        )
        run(
            c,
            "curl -s -m 8 -o /tmp/jl.txt -w 'jobs=%{http_code} ctype=%{content_type} t=%{time_total}\\n' "
            "-X POST http://127.0.0.1/jobs/listen -H 'Content-Type: application/json' "
            "-d '{\"_mid\":0,\"data\":{\"id\":\"x\"}}'; head -c 80 /tmp/jl.txt; echo",
            timeout=30,
        )
        run(c, "curl -s -m 5 -o /tmp/dl.txt -w 'dl=%{http_code} ctype=%{content_type}\\n' http://127.0.0.1/dl/a/b/c; head -c 40 /tmp/dl.txt; echo")
        run(c, "curl -s -m 5 -o /dev/null -w 'api_direct_6080=%{http_code}\\n' http://127.0.0.1:6080/api/v1/health")
    finally:
        c.close()
    print("\nDone. Open http://192.168.100.89/", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
