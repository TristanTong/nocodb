#!/usr/bin/env python3
"""Fix docker iptables on 100.89, then start mlnocodb."""
import os
import sys
import time
import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")


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
        run(c, "iptables -t nat -L DOCKER -n 2>&1 | head -5 || true")
        print("restart docker to recreate iptables chains...", flush=True)
        run(c, "systemctl restart docker", timeout=120)
        time.sleep(8)
        run(c, "systemctl is-active docker; docker ps --format '{{.Names}} {{.Status}}' | head")
        run(c, "iptables -t nat -L DOCKER -n 2>&1 | head -8")

        # ensure postgres still up
        run(c, "docker start postgres 2>&1; docker ps --filter name=postgres --format '{{.Names}} {{.Status}} {{.Ports}}'")

        run(c, "docker network rm mlnocodb_default 2>/dev/null || true")
        code, _ = run(c, "cd /opt/mlnocodb && docker compose up -d 2>&1")
        if code != 0:
            # fallback: run without compose network (host network / default bridge)
            print("compose failed — fallback docker run on default bridge", flush=True)
            run(c, "docker rm -f mlnocodb-api mlnocodb-ui 2>/dev/null || true")
            run(
                c,
                "docker run -d --name mlnocodb-api --restart always "
                "-p 6080:8080 "
                "-e 'NC_DB=pg://192.168.100.89:5432?u=postgres&p=Pass%40w0rd&d=mlnoco' "
                "-e NC_DISABLE_TELE=true "
                "-e 'NC_PUBLIC_URL=http://192.168.100.89:6080' "
                "-e TZ=Asia/Shanghai "
                "-v /opt/mlnocodb/data:/usr/app/data "
                "--add-host=host.docker.internal:host-gateway "
                "mlnocodb:0.1.3",
            )
            run(
                c,
                "docker run -d --name mlnocodb-ui --restart always "
                "-p 6100:6100 "
                "-w /app "
                "-e PORT=6100 -e NITRO_HOST=0.0.0.0 -e NITRO_PORT=6100 "
                "-e 'NUXT_PUBLIC_NC_BACKEND_URL=http://192.168.100.89:6080' "
                "-e NUXT_PAGE_TRANSITION_DISABLE=true -e TZ=Asia/Shanghai "
                "-v /opt/mlnocodb/ui-output:/app:ro "
                "node:22-slim node server/index.mjs",
            )

        time.sleep(30)
        run(c, "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'")
        run(c, "docker logs --tail 40 mlnocodb-api 2>&1")
        run(c, "docker logs --tail 10 mlnocodb-ui 2>&1")
        run(
            c,
            "curl -s -m 15 -X POST http://127.0.0.1:6080/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' -d '{\"email\":\"a@b.c\",\"password\":\"x\"}'",
        )
        run(c, "curl -s -m 10 -o /dev/null -w 'UI=%{http_code}\\n' http://127.0.0.1:6100/")
        run(c, "docker inspect mlnocodb-api --format '{{range .Config.Env}}{{println .}}{{end}}' | grep NC_")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
