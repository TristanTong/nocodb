#!/usr/bin/env python3
"""Restart API on 93 to flush meta cache after hide_autogen Meta SQL."""
from __future__ import annotations

import os
import time

import paramiko

HOST93 = "192.168.100.93"
PWD93 = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST93, username="root", password=PWD93, timeout=30)

    def run(cmd: str, t: int = 120) -> tuple[int, str]:
        _, o, e = c.exec_command(cmd, timeout=t)
        out = o.read().decode("utf-8", "replace")
        err = e.read().decode("utf-8", "replace")
        code = o.channel.recv_exit_status()
        print("CMD", cmd[:200], flush=True)
        if out.strip():
            print(out[-3000:], flush=True)
        if err.strip():
            print("ERR", err[-800:], flush=True)
        print("exit", code, flush=True)
        return code, out

    try:
        run("docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'")
        # find compose dir used previously
        run(
            "bash -lc \"find /opt /root /home /data /mnt -maxdepth 4 "
            "-name 'docker-compose*.yml' 2>/dev/null | head -30\""
        )
        # restart api container by name patterns
        code, out = run(
            "bash -lc \"docker ps --format '{{.Names}}' | "
            "grep -Ei 'api|nocodb|mlnocodb' || true\""
        )
        names = [n.strip() for n in out.splitlines() if n.strip()]
        print("candidates", names, flush=True)
        target = None
        for n in names:
            if "api" in n.lower() or "nocodb" in n.lower() or "mlno" in n.lower():
                target = n
                break
        if not target and names:
            target = names[0]
        if not target:
            print("NO_CONTAINER", flush=True)
            return 1
        print("restarting", target, flush=True)
        run(f"docker restart {target}", t=180)
        # wait health via nginx or direct
        ok = False
        for i in range(30):
            time.sleep(2)
            for url in (
                "http://127.0.0.1:8080/api/v1/health",
                "http://127.0.0.1:8080/dashboard",
                "http://127.0.0.1:6080/api/v1/health",
            ):
                code, hout = run(
                    f"bash -lc \"curl -sS -o /dev/null -w '%{{http_code}}' {url} || echo FAIL\""
                )
                if "200" in hout or "302" in hout:
                    ok = True
                    break
            if ok:
                break
        print("READY" if ok else "NOT_READY", flush=True)
        return 0 if ok else 2
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
