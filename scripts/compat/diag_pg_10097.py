#!/usr/bin/env python3
"""Diagnose PG 100.97 protocol-level connectivity from server 100.93."""
import os
import sys

import paramiko

HOST = "192.168.100.93"

# python3 socket test: TCP connect + PG SSLRequest + StartupMessage-ish
SOCK_TEST = r"""
import socket, struct, sys
s = socket.socket(); s.settimeout(5)
try:
    s.connect(('192.168.100.97', 5432)); print('TCP_CONNECT_OK')
except Exception as e:
    print('TCP_CONNECT_FAIL', e); sys.exit(0)
# SSLRequest: len=8, code=80877103
try:
    s.sendall(struct.pack('!II', 8, 80877103))
    r = s.recv(1)
    print('SSL_RESP', r)
except Exception as e:
    print('SSL_REQ_FAIL', e)
s.close()
"""

CMDS = [
    ("socket+sslrequest test", f"python3 -c \"{SOCK_TEST.strip()}\""),
    ("psql with connect_timeout",
     "timeout 20 docker run --rm postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/postgres?connect_timeout=5' -c 'select version();' 2>&1"),
    ("psql list databases",
     "timeout 20 docker run --rm postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/postgres?connect_timeout=5' -tAc \"select datname from pg_database where datname not in ('template0','template1')\" 2>&1"),
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
