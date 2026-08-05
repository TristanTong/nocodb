#!/usr/bin/env python3
"""Isolate 100.93 -> 100.97 PG blockage: host vs docker, TCP vs protocol."""
import os
import sys

import paramiko

HOST = "192.168.100.93"

HOST_PROTO = r"""exec 3<>/dev/tcp/192.168.100.97/5432 && printf '\x00\x00\x00\x08\x04\xd2\x16\x2f' >&3 && timeout 6 dd bs=1 count=1 <&3 2>/dev/null | od -An -tx1; exec 3<&- 3>&-"""

CMDS = [
    ("host tcp+sslrequest", HOST_PROTO),
    ("docker tcp connect (nc)", "docker run --rm postgres:15-alpine nc -z -w5 192.168.100.97 5432 && echo DOCKER_TCP_OK || echo DOCKER_TCP_FAIL"),
    ("docker sslrequest via nc",
     "docker run --rm postgres:15-alpine sh -c \"printf '\\x00\\x00\\x00\\x08\\x04\\xd2\\x16\\x2f' | nc -w 6 192.168.100.97 5432 | od -An -tx1 | head -3\""),
    ("iptables output drops", "iptables -L OUTPUT -n -v 2>/dev/null | head -20; iptables-save 2>/dev/null | grep -E '100\\.97|DROP|REJECT' | grep -v '^#' | head -20 || true"),
    ("firewalld", "systemctl is-active firewalld 2>/dev/null; firewall-cmd --list-all 2>/dev/null | head -15"),
    ("route/arp to 100.97", "ip route get 192.168.100.97; ip neigh show 192.168.100.97"),
]


def main():
    pwd = os.environ.get("REMOTE_SSH_PASSWORD", "")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=pwd, timeout=30)
    try:
        for title, cmd in CMDS:
            print(f"\n=== {title}")
            _, o, e = c.exec_command(cmd, timeout=90)
            out = o.read().decode("utf-8", "replace")
            err = e.read().decode("utf-8", "replace")
            if out.strip():
                print(out.rstrip())
            if err.strip():
                print(err.rstrip())
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
