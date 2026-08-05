#!/usr/bin/env python3
"""Fix nginx: proxy /jobs /download /dltemp to API; reload nginx."""
import os
import time

import paramiko

HOST = "192.168.100.93"

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

    # shared proxy headers
    map $http_upgrade $connection_upgrade {
        default upgrade;
        '' close;
    }

    server {
        listen 80;
        server_name _;

        # NocoDB API
        location /api/ {
            proxy_pass http://api:8080;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
            proxy_send_timeout 300s;
        }

        # Job status long-poll (CSV/JSON/Excel download completion)
        # MUST hit API; otherwise UI returns HTML and export stuck on "Preparing..."
        location /jobs/ {
            proxy_pass http://api:8080;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            # jobs.listen holds connection up to ~30s
            proxy_read_timeout 120s;
            proxy_send_timeout 120s;
        }

        # Local storage download links for exported files / attachments
        location /download/ {
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

        # WebSocket (Socket.io)
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

        # Frontend UI
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


def run(c, cmd, timeout=60):
    print(f"$ {cmd}")
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip()[:2000])
    if err.strip():
        print(err.rstrip()[:500])
    return code, out, err


def main():
    pwd = os.environ["REMOTE_SSH_PASSWORD"]
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=pwd, timeout=30)
    try:
        print("=== backup nginx.conf ===")
        run(c, "cp -a /opt/mlnocodb/nginx.conf /opt/mlnocodb/nginx.conf.bak.$(date +%Y%m%d%H%M%S)")

        print("=== write fixed nginx.conf ===")
        sftp = c.open_sftp()
        with sftp.file("/opt/mlnocodb/nginx.conf", "w") as f:
            f.write(NGINX)
        sftp.close()

        print("=== test & reload nginx ===")
        code, out, err = run(c, "docker exec mlnocodb-nginx nginx -t")
        if code != 0:
            print("nginx -t failed, abort")
            return 1
        run(c, "docker exec mlnocodb-nginx nginx -s reload")
        time.sleep(1)

        print("=== verify /jobs/listen now hits API (expect JSON/auth error, NOT HTML) ===")
        run(
            c,
            "curl -s -m 8 -o /tmp/jfix.txt -w 'code=%{http_code} ctype=%{content_type}\\n' "
            "-X POST http://127.0.0.1/jobs/listen -H 'Content-Type: application/json' "
            "-d '{\"_mid\":0,\"data\":{\"id\":\"x\"}}'; head -c 250 /tmp/jfix.txt; echo",
        )

        print("\n=== verify /download goes to API ===")
        run(
            c,
            "curl -s -m 5 -o /tmp/dl.txt -w 'code=%{http_code} ctype=%{content_type}\\n' "
            "http://127.0.0.1/download/noco/test; head -c 150 /tmp/dl.txt; echo",
        )

        print("\n=== UI still OK ===")
        run(c, "curl -s -m 5 -o /dev/null -w 'UI=%{http_code}\\n' http://127.0.0.1/")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
