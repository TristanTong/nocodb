#!/usr/bin/env python3
"""Inspect FORWARD chain and fix docker bridge forwarding to LAN on 100.93."""
import os
import re
import sys

import paramiko

HOST = "192.168.100.93"


def run(c, cmd, timeout=60, show=True):
    if show:
        print(f"$ {cmd}")
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if show and out.strip():
        print(out.rstrip())
    if show and err.strip() and code != 0:
        print(err.rstrip(), file=sys.stderr)
    return code, out, err


def main():
    pwd = os.environ.get("REMOTE_SSH_PASSWORD", "")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=pwd, timeout=30)
    try:
        print("=== FORWARD chain (before)")
        run(c, "iptables -L FORWARD -n -v --line-numbers | head -25")

        print("\n=== docker networks")
        _, nets, _ = run(c, "docker network ls --format '{{.Name}}'")
        subnets = []
        for net in nets.split():
            if net in ("bridge", "host", "none"):
                continue
            _, out, _ = run(c, f"docker network inspect {net} --format '{{{{range .IPAM.Config}}}}{{{{.Subnet}}}} {{{{end}}}}'", show=False)
            for s in out.split():
                subnets.append((net, s.strip()))
        # default docker0
        _, out, _ = run(c, "docker network inspect bridge --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}'", show=False)
        for s in out.split():
            subnets.append(("bridge", s.strip()))
        subnets = [(n, s) for n, s in subnets if re.match(r"^\d+\.\d+\.\d+\.\d+/\d+$", s)]
        print(subnets)

        print("\n=== insert ACCEPT rules at FORWARD top")
        for _, s in subnets:
            run(c, f"iptables -C FORWARD -s {s} -j ACCEPT 2>/dev/null || iptables -I FORWARD 1 -s {s} -j ACCEPT")
            run(c, f"iptables -C FORWARD -d {s} -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || iptables -I FORWARD 1 -d {s} -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT")

        print("\n=== FORWARD chain (after)")
        run(c, "iptables -L FORWARD -n -v --line-numbers | head -15")

        print("\n=== test from container")
        run(c, "docker run --rm postgres:15-alpine nc -z -w5 192.168.100.97 5432 && echo DOCKER_TCP_OK || echo DOCKER_TCP_FAIL")
        run(c, "timeout 20 docker run --rm postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco?connect_timeout=5' -tAc \"select count(*) from information_schema.tables where table_schema='public'\" 2>&1")

        print("\n=== persist via firewalld direct rules")
        for _, s in subnets:
            run(c, f"firewall-cmd --permanent --direct --add-rule ipv4 filter FORWARD 0 -s {s} -j ACCEPT 2>&1 | tail -1")
            run(c, f"firewall-cmd --permanent --direct --add-rule ipv4 filter FORWARD 0 -d {s} -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>&1 | tail -1")

        print("\n=== check mlnocodb-api recovery")
        run(c, "docker ps --format '{{.Names}}\\t{{.Status}}' | grep mlnocodb")
        run(c, "sleep 30; docker logs --tail 12 mlnocodb-api 2>&1", timeout=90)
        run(c, "docker ps --format '{{.Names}}\\t{{.Status}}' | grep mlnocodb")
        run(c, "curl -s -m 10 -X POST http://localhost:6080/api/v1/auth/user/signin -H 'Content-Type: application/json' -d '{\"email\":\"nonexistent@x.com\",\"password\":\"wrong\"}' | head -c 300; echo")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
