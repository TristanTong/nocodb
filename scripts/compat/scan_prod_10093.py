#!/usr/bin/env python3
"""Scan production mlnocodb config + ports on 192.168.100.93."""
from __future__ import annotations

import os
import socket
import sys
import time

import paramiko

HOST = "192.168.100.93"
PG = "192.168.100.97"


def tcp(host: str, port: int, timeout: float = 3.0) -> str:
    s = socket.socket()
    s.settimeout(timeout)
    t0 = time.time()
    try:
        s.connect((host, port))
        ms = int((time.time() - t0) * 1000)
        return f"OPEN  {ms}ms"
    except Exception as e:
        return f"CLOSED/FAIL ({type(e).__name__}: {e})"
    finally:
        s.close()


def run(c, cmd, timeout=60):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    return code, out, err


def main():
    print("=" * 60)
    print("LOCAL TCP probe (from this PC)")
    print("=" * 60)
    targets = [
        (HOST, 22, "SSH"),
        (HOST, 80, "UI"),
        (HOST, 6080, "API"),
        (HOST, 443, "HTTPS/nginx"),
        (HOST, 8080, "nginx:80 map"),
        (HOST, 5432, "local docker PG (dify)"),
        (PG, 5432, "Meta PostgreSQL"),
        (PG, 22, "PG host SSH"),
    ]
    for h, p, label in targets:
        print(f"  {h}:{p:<5}  {label:<22} {tcp(h, p)}")

    pwd = os.environ.get("REMOTE_SSH_PASSWORD", "")
    if not pwd:
        print("\nREMOTE_SSH_PASSWORD not set; skip remote inspect", file=sys.stderr)
        return 2

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=pwd, timeout=30)
    try:
        print("\n" + "=" * 60)
        print(f"REMOTE host overview ({HOST})")
        print("=" * 60)
        _, out, _ = run(c, "hostname; date; uptime; cat /etc/centos-release 2>/dev/null || cat /etc/redhat-release 2>/dev/null")
        print(out.rstrip())

        print("\n--- IP addresses ---")
        _, out, _ = run(c, "ip -4 addr show | grep -E 'inet |^[0-9]'")
        print(out.rstrip())

        print("\n--- listening ports (key) ---")
        _, out, _ = run(c, "ss -tlnp | grep -E ':(22|80|443|5432|6080|8080|5003)\\s' || true")
        print(out.rstrip() or "(none)")

        print("\n--- docker mlnocodb containers ---")
        _, out, _ = run(
            c,
            "docker ps -a --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'",
        )
        print(out.rstrip())

        print("\n--- mlnocodb-api env ---")
        _, out, _ = run(
            c,
            "docker inspect mlnocodb-api --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep -E '^(NC_|TZ=|PORT=|NODE_ENV=)' || echo NO_API",
        )
        print(out.rstrip())

        print("\n--- mlnocodb-ui env ---")
        _, out, _ = run(
            c,
            "docker inspect mlnocodb-ui --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep -E '^(NUXT_|PORT=|NITRO_|TZ=)' || echo NO_UI",
        )
        print(out.rstrip())

        print("\n--- mounts ---")
        _, out, _ = run(
            c,
            "docker inspect mlnocodb-api mlnocodb-ui --format '{{.Name}} {{range .Mounts}}{{.Source}}->{{.Destination}}({{.RW}}) {{end}}' 2>/dev/null",
        )
        print(out.rstrip())

        print("\n--- compose file ---")
        _, out, _ = run(c, "test -f /opt/mlnocodb/docker-compose.yml && grep -E 'image:|NC_DB|NC_PUBLIC|NUXT_PUBLIC|ports:|\"[0-9]' /opt/mlnocodb/docker-compose.yml || echo NO_COMPOSE")
        print(out.rstrip())

        print("\n--- disk /opt/mlnocodb ---")
        _, out, _ = run(c, "du -sh /opt/mlnocodb/* 2>/dev/null; ls -la /opt/mlnocodb/")
        print(out.rstrip())

        print("\n--- host -> PG 100.97 ---")
        _, out, _ = run(
            c,
            "timeout 5 bash -c '</dev/tcp/%s/5432' && echo HOST_TCP_OK || echo HOST_TCP_FAIL" % PG,
        )
        print(out.rstrip())

        print("\n--- container -> PG 100.97 ---")
        _, out, _ = run(
            c,
            "docker run --rm --network mlnocodb_default postgres:15-alpine nc -z -w5 %s 5432 && echo CTR_TCP_OK || echo CTR_TCP_FAIL" % PG,
            timeout=90,
        )
        print(out.rstrip())
        _, out, _ = run(
            c,
            "timeout 20 docker run --rm --network mlnocodb_default postgres:15-alpine "
            "psql 'postgresql://postgres:Pass%%40w0rd@%s:5432/mlnoco?connect_timeout=5' "
            "-tAc \"select current_database()||' tables='||count(*) from information_schema.tables where table_schema='public'\" 2>&1" % PG,
            timeout=60,
        )
        print(out.rstrip())

        print("\n--- HTTP health (on host) ---")
        checks = [
            ("UI /", "curl -s -m 8 -o /dev/null -w '%{http_code} %{time_total}s' http://127.0.0.1:80/"),
            ("API signin", "curl -s -m 8 -o /tmp/nc_signin.json -w '%{http_code} %{time_total}s' -X POST http://127.0.0.1:6080/api/v1/auth/user/signin -H 'Content-Type: application/json' -d '{\"email\":\"x@x.com\",\"password\":\"y\"}'; echo; head -c 120 /tmp/nc_signin.json; echo"),
            ("API v2 bases", "curl -s -m 8 -o /dev/null -w '%{http_code} %{time_total}s' http://127.0.0.1:6080/api/v2/meta/bases"),
        ]
        for label, cmd in checks:
            _, out, _ = run(c, cmd)
            print(f"  {label}: {out.strip()}")

        print("\n--- api restart / recent errors ---")
        _, out, _ = run(c, "docker inspect mlnocodb-api --format 'RestartCount={{.RestartCount}} StartedAt={{.State.StartedAt}}'")
        print(out.rstrip())
        _, out, _ = run(c, "docker logs --since 24h mlnocodb-api 2>&1 | grep -iE 'error|exception|timeout|ECONN|fail' | tail -15 || echo NO_RECENT_ERRORS")
        print(out.rstrip() or "NO_RECENT_ERRORS")

        print("\n--- other containers (brief) ---")
        _, out, _ = run(
            c,
            "docker ps --format '{{.Names}}\\t{{.Status}}\\t{{.Ports}}' | grep -v mlnocodb | head -20",
        )
        print(out.rstrip())

        print("\n--- firewalld ports ---")
        _, out, _ = run(c, "firewall-cmd --list-ports 2>/dev/null; firewall-cmd --list-services 2>/dev/null")
        print(out.rstrip())
    finally:
        c.close()

    print("\n" + "=" * 60)
    print("EXTERNAL HTTP from this PC")
    print("=" * 60)
    try:
        import urllib.request

        for url in [
            f"http://{HOST}/",
            f"http://{HOST}:6080/api/v2/meta/bases",
        ]:
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=8) as resp:
                    print(f"  {url} -> {resp.status}")
            except Exception as e:
                code = getattr(getattr(e, "code", None), "__int__", lambda: None)()
                if hasattr(e, "code"):
                    print(f"  {url} -> HTTP {e.code}")
                else:
                    print(f"  {url} -> FAIL {e}")
    except Exception as e:
        print("urllib failed", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
