#!/usr/bin/env python3
"""Probe upload-related paths via nginx:80 vs api:6080 on prod."""
import os
import paramiko

HOST = "192.168.100.93"

PATHS = [
    # likely API (under /api/)
    "/api/v1/db/storage/upload",
    "/api/v2/storage/upload",
    "/api/v1/db/meta/projects",
    # non-/api paths that might be upload-related
    "/upload",
    "/uploads",
    "/nc/uploads",
    "/download/test",
    "/dltemp/test",
    "/jobs/listen",
]


def run(c, cmd):
    _, o, e = c.exec_command(cmd, timeout=20)
    return o.read().decode("utf-8", "replace").strip()


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=os.environ["REMOTE_SSH_PASSWORD"], timeout=30)
    try:
        print("=== nginx.conf locations ===")
        print(run(c, "grep -E 'location |proxy_pass' /opt/mlnocodb/nginx.conf"))
        print("\n=== path probe (OPTIONS/GET) nginx vs api ===")
        for p in PATHS:
            # POST empty to see if HTML (UI) or JSON/API error
            cmd = (
                f"echo -n '{p} | '; "
                f"curl -s -m 5 -o /tmp/n.bin -w 'nginx=%{{http_code}}:%{{content_type}} ' "
                f"-X POST 'http://127.0.0.1{p}' -H 'Content-Type: multipart/form-data; boundary=x' -d '--x--'; "
                f"head -c 40 /tmp/n.bin | tr '\\n' ' '; echo -n ' || '; "
                f"curl -s -m 5 -o /tmp/a.bin -w 'api=%{{http_code}}:%{{content_type}} ' "
                f"-X POST 'http://127.0.0.1:6080{p}' -H 'Content-Type: multipart/form-data; boundary=x' -d '--x--'; "
                f"head -c 40 /tmp/a.bin | tr '\\n' ' '; echo"
            )
            print(run(c, cmd))
    finally:
        c.close()


if __name__ == "__main__":
    main()
