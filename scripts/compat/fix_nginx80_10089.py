#!/usr/bin/env python3
"""Fix crash-looping mlnocodb-nginx on 100.89."""
import os
import sys
import time
import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")


def run(c, cmd, timeout=120):
    print(f"$ {cmd}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    print(out.encode("ascii", "replace").decode().rstrip()[:3000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(c, "docker logs --tail 40 mlnocodb-nginx 2>&1")
        run(c, "ls -la /opt/mlnocodb/nginx.conf; wc -l /opt/mlnocodb/nginx.conf; head -20 /opt/mlnocodb/nginx.conf")
        # test config with temporary container
        run(
            c,
            "docker run --rm -v /opt/mlnocodb/nginx.conf:/etc/nginx/nginx.conf:ro nginx:alpine nginx -t 2>&1",
        )

        # Common alpine issue: include /etc/nginx/mime.types exists; pid /tmp ok.
        # Maybe CRLF line endings from Windows write?
        run(c, "file /opt/mlnocodb/nginx.conf; od -c /opt/mlnocodb/nginx.conf | head -3")
        run(c, "sed -i 's/\\r$//' /opt/mlnocodb/nginx.conf")
        run(
            c,
            "docker run --rm -v /opt/mlnocodb/nginx.conf:/etc/nginx/nginx.conf:ro nginx:alpine nginx -t 2>&1",
        )

        run(c, "docker rm -f mlnocodb-nginx 2>/dev/null || true")
        run(c, "cd /opt/mlnocodb && docker compose up -d nginx 2>&1")
        time.sleep(5)
        run(c, "docker ps -a --filter name=mlnocodb-nginx --format '{{.Names}} {{.Status}} {{.Ports}}'")
        run(c, "docker logs --tail 20 mlnocodb-nginx 2>&1")

        # if still failing, try security_opt like production
        code, out = run(c, "docker inspect mlnocodb-nginx --format '{{.State.Status}} {{.State.ExitCode}}'")
        if "running" not in out:
            print("still not running — recreate with seccomp unconfined", flush=True)
            # patch compose
            run(c, "grep -n security_opt /opt/mlnocodb/docker-compose.yml || true")
            # manual run for debug
            run(
                c,
                "docker run -d --name mlnocodb-nginx --restart always "
                "--network mlnocodb_default -p 80:80 "
                "--security-opt seccomp=unconfined "
                "-v /opt/mlnocodb/nginx.conf:/etc/nginx/nginx.conf:ro "
                "nginx:alpine 2>&1",
            )
            time.sleep(3)
            run(c, "docker ps -a --filter name=mlnocodb-nginx --format '{{.Names}} {{.Status}}'")
            run(c, "docker logs --tail 30 mlnocodb-nginx 2>&1")

        time.sleep(3)
        run(c, "curl -s -m 8 -o /dev/null -w 'UI80=%{http_code}\\n' http://127.0.0.1/")
        run(
            c,
            "curl -s -m 8 -X POST http://127.0.0.1/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' -d '{\"email\":\"a@b.c\",\"password\":\"x\"}'",
        )
        run(
            c,
            "curl -s -m 6 -o /tmp/j.txt -w 'jobs=%{http_code} ctype=%{content_type}\\n' "
            "-X POST http://127.0.0.1/jobs/listen -H 'Content-Type: application/json' "
            "-d '{\"_mid\":0,\"data\":{\"id\":\"x\"}}'; head -c 60 /tmp/j.txt; echo",
            timeout=20,
        )
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
