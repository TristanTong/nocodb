#!/usr/bin/env python3
"""Confirm nginx misroutes /jobs/listen and other non-/api paths to UI."""
import os
import paramiko

HOST = "192.168.100.93"


def run(c, cmd):
    print(f"$ {cmd}")
    _, o, e = c.exec_command(cmd, timeout=30)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    if out.strip():
        print(out.rstrip()[:1500])
    if err.strip():
        print(err.rstrip()[:300])


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=os.environ["REMOTE_SSH_PASSWORD"], timeout=30)
    try:
        print("=== /jobs/listen via nginx:80 (likely wrong -> UI) ===")
        run(c, "curl -s -m 8 -o /tmp/j1.txt -w 'code=%{http_code} ctype=%{content_type}\\n' -X POST http://127.0.0.1/jobs/listen -H 'Content-Type: application/json' -d '{\"_mid\":0,\"data\":{\"id\":\"x\"}}'; head -c 200 /tmp/j1.txt; echo")

        print("\n=== /jobs/listen via API:6080 (correct) ===")
        run(c, "curl -s -m 8 -o /tmp/j2.txt -w 'code=%{http_code} ctype=%{content_type}\\n' -X POST http://127.0.0.1:6080/jobs/listen -H 'Content-Type: application/json' -d '{\"_mid\":0,\"data\":{\"id\":\"x\"}}'; head -c 300 /tmp/j2.txt; echo")

        print("\n=== other API paths that may bypass /api/ ===")
        for path in [
            "/download/noco/test",
            "/dltemp/test",
            "/nc/uploads/test",
            "/api/v2/health",
            "/api/v1/health",
        ]:
            run(c, f"curl -s -m 5 -o /dev/null -w '{path} nginx=%{{http_code}} ' http://127.0.0.1{path}; curl -s -m 5 -o /dev/null -w 'api=%{{http_code}}\\n' http://127.0.0.1:6080{path}")

        print("\n=== nginx.conf current ===")
        run(c, "cat /opt/mlnocodb/nginx.conf")
    finally:
        c.close()


if __name__ == "__main__":
    main()
