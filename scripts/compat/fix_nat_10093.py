#!/usr/bin/env python3
"""Check ip_forward + NAT MASQUERADE on 100.93 and fix docker outbound."""
import os
import sys

import paramiko

HOST = "192.168.100.93"

BRIDGES = [("172.17.0.0/16", "docker0"), ("172.18.0.0/16", "br-9db71a760b2e"),
           ("172.19.0.0/16", "br-db9bee026689"), ("172.20.0.0/16", "br-57a6a75deaa8")]


def run(c, cmd, timeout=60):
    print(f"$ {cmd}")
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip())
    if err.strip() and code != 0:
        print(err.rstrip(), file=sys.stderr)
    return code, out, err


def main():
    pwd = os.environ.get("REMOTE_SSH_PASSWORD", "")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=pwd, timeout=30)
    try:
        print("=== ip_forward")
        run(c, "sysctl net.ipv4.ip_forward; cat /proc/sys/net/ipv4/ip_forward")

        print("\n=== nat POSTROUTING")
        run(c, "iptables -t nat -L POSTROUTING -n -v --line-numbers")

        print("\n=== bridge name map")
        run(c, "docker network ls --no-trunc --format '{{.ID}} {{.Name}}'")
        run(c, "ip -o link show type bridge | awk '{print $2}'")

        print("\n=== ensure ip_forward=1")
        run(c, "sysctl -w net.ipv4.ip_forward=1")
        run(c, "grep -q '^net.ipv4.ip_forward' /etc/sysctl.conf && sed -i 's/^net.ipv4.ip_forward.*/net.ipv4.ip_forward = 1/' /etc/sysctl.conf || echo 'net.ipv4.ip_forward = 1' >> /etc/sysctl.conf")

        print("\n=== ensure MASQUERADE rules")
        for subnet, br in BRIDGES:
            run(c, f"iptables -t nat -C POSTROUTING -s {subnet} ! -o {br} -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s {subnet} ! -o {br} -j MASQUERADE")

        print("\n=== nat POSTROUTING (after)")
        run(c, "iptables -t nat -L POSTROUTING -n -v --line-numbers | head -15")

        print("\n=== retest container -> 100.97")
        run(c, "docker run --rm postgres:15-alpine nc -z -w5 192.168.100.97 5432 && echo DOCKER_TCP_OK || echo DOCKER_TCP_FAIL", timeout=120)
        run(c, "timeout 20 docker run --rm postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco?connect_timeout=5' -tAc \"select count(*) from information_schema.tables where table_schema='public'\" 2>&1", timeout=60)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
