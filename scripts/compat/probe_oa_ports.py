#!/usr/bin/env python3
"""Probe public mapping IP ports and compare with common HTTP ports."""
from __future__ import annotations

import socket
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

IP = "120.197.111.148"
PORTS = [80, 443, 8080, 8443, 6080, 6100, 19999, 8000, 8001]


def tcp(ip, port, timeout=4):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        return True, ""
    except Exception as e:
        return False, str(e)
    finally:
        s.close()


def http(url, timeout=6):
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(120)
            return r.status, r.getheader("Server"), r.getheader("Content-Type"), body
    except Exception as e:
        return None, None, None, str(e)


def main():
    print(f"probe {IP}", flush=True)
    for p in PORTS:
        ok, err = tcp(IP, p)
        print(f"  tcp {p:5d}  {'OPEN' if ok else 'FAIL'}  {err}", flush=True)

    for url in [
        f"http://{IP}/",
        f"http://{IP}:19999/",
        f"http://{IP}:19999/api/v1/health",
        "http://oa.medlinket.com/",
        "http://oa.medlinket.com:19999/api/v1/health",
        "https://oa.medlinket.com/",
    ]:
        st, server, ctype, body = http(url)
        print(f"\nGET {url}\n  status={st} server={server} type={ctype}\n  body={body!r}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
