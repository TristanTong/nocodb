#!/usr/bin/env python3
"""Add /dl/ to nginx (attachment legacy download path); verify upload paths."""
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

    map $http_upgrade $connection_upgrade {
        default upgrade;
        '' close;
    }

    server {
        listen 80;
        server_name _;

        # Upload + all REST APIs
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

        # CSV/JSON/Excel export job long-poll
        location /jobs/ {
            proxy_pass http://api:8080;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 120s;
            proxy_send_timeout 120s;
        }

        # Attachment / export file downloads (NOT under /api/)
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


def run(c, cmd, timeout=60):
    print(f"$ {cmd}")
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip()[:1500])
    if err.strip() and code != 0:
        print(err.rstrip()[:400])
    return code


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=os.environ["REMOTE_SSH_PASSWORD"], timeout=30)
    try:
        run(c, "cp -a /opt/mlnocodb/nginx.conf /opt/mlnocodb/nginx.conf.bak.$(date +%Y%m%d%H%M%S)")
        sftp = c.open_sftp()
        with sftp.file("/opt/mlnocodb/nginx.conf", "w") as f:
            f.write(NGINX)
        sftp.close()
        if run(c, "docker exec mlnocodb-nginx nginx -t") != 0:
            return 1
        run(c, "docker exec mlnocodb-nginx nginx -s reload")
        time.sleep(1)
        print("\n=== verify /dl/ now API ===")
        run(c, "curl -s -m 5 -o /tmp/dl.bin -w 'code=%{http_code} ctype=%{content_type}\\n' http://127.0.0.1/dl/a/b/c; head -c 80 /tmp/dl.bin; echo")
        print("\n=== verify upload still /api/ ===")
        run(c, "curl -s -m 5 -o /tmp/up.bin -w 'code=%{http_code} ctype=%{content_type}\\n' -X POST http://127.0.0.1/api/v1/db/storage/upload; head -c 120 /tmp/up.bin; echo")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
