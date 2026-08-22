#!/usr/bin/env python3
"""Diagnose why oa.medlinket.com:19999 is only reachable from some networks."""
from __future__ import annotations

import os
import socket
import sys
import urllib.request

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")
DOMAIN = "oa.medlinket.com"
PORT = 19999


def run(c, cmd, timeout=40):
    print(f"\n$ {cmd[:280]}", flush=True)
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip()[:6000], flush=True)
    print(f"exit={code}", flush=True)
    return code, out


def local_dns():
    print("=== local DNS / TCP from this PC ===", flush=True)
    try:
        infos = socket.getaddrinfo(DOMAIN, PORT, type=socket.SOCK_STREAM)
        ips = sorted({x[4][0] for x in infos})
        print(f"resolve {DOMAIN} -> {ips}", flush=True)
    except Exception as e:
        print(f"resolve fail: {e}", flush=True)
        ips = []
    for ip in ips[:4]:
        s = socket.socket()
        s.settimeout(5)
        try:
            s.connect((ip, PORT))
            print(f"tcp {ip}:{PORT} OPEN", flush=True)
        except Exception as e:
            print(f"tcp {ip}:{PORT} FAIL {e}", flush=True)
        finally:
            s.close()
    try:
        req = urllib.request.Request(
            f"http://{DOMAIN}:{PORT}/api/v1/health",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            print(f"http health {r.status} {r.read()[:200]}", flush=True)
    except Exception as e:
        print(f"http health fail: {e}", flush=True)


def main():
    local_dns()
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(c, "hostname; ip -4 addr show | grep -E 'inet |state'")
        run(c, f"getent hosts {DOMAIN}; ping -c 1 -W 2 {DOMAIN} | head -3")
        run(
            c,
            "ss -lntp | grep -E ':80|:6080|:6100|:19999' ; "
            "iptables -L INPUT -n --line-numbers | head -40",
        )
        run(
            c,
            "systemctl is-active firewalld; firewall-cmd --state 2>/dev/null; "
            "firewall-cmd --list-all 2>/dev/null | head -40",
        )
        run(
            c,
            "echo '=== recent nginx access by client ==='; "
            "docker logs --since 30m mlnocodb-nginx 2>&1 | "
            "awk '{print $1}' | grep -E '^[0-9.]+$' | sort | uniq -c | sort -nr | head -30",
        )
        run(
            c,
            "echo '=== last 25 nginx lines ==='; docker logs --tail 25 mlnocodb-nginx 2>&1",
        )
        run(
            c,
            "echo '=== public IP seen by 100.89 ==='; "
            "curl -s -m 8 ifconfig.me; echo; curl -s -m 8 ipinfo.io/ip; echo; "
            "curl -s -m 8 https://api.ipify.org; echo",
        )
        run(
            c,
            f"echo '=== curl domain from 100.89 ==='; "
            f"curl -sv -m 8 http://{DOMAIN}:{PORT}/api/v1/health 2>&1 | tail -40",
        )
        run(
            c,
            "echo '=== default route / neigh ==='; ip route; echo; "
            "ip neigh | grep -E '192.168.100.|192.168.1.' | head -20",
        )
        run(
            c,
            "echo '=== docker published ports ==='; "
            "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Ports}}\\t{{.Status}}'",
        )
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
