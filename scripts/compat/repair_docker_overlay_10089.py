#!/usr/bin/env python3
"""Repair 100.89 mlnocodb: remove corrupt containers, recreate from intact images.

Does NOT touch host postgres Meta DB or /opt/mlnocodb/data / ui-output.
"""
from __future__ import annotations

import os
import time

import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")
REMOTE = "/opt/mlnocodb"


def ssh():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    return c


def run(c, cmd, timeout=600, check=True):
    print(f"$ {cmd[:240]}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out[-5000:], flush=True)
    if err.strip() and (code or "error" in err.lower()):
        print("STDERR:", err[-1500:], flush=True)
    if check and code:
        raise SystemExit(f"fail {code}: {cmd}\n{err[-600:]}\n{out[-400:]}")
    return code, out, err


def main() -> int:
    c = ssh()
    try:
        # 0) snapshot state
        run(c, "docker images --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}' | grep -E 'mlnocodb|nginx|node' | head -30", check=False)
        run(c, f"cd {REMOTE} && cp -a docker-compose.yml docker-compose.yml.bak.repair-$(date +%Y%m%d%H%M%S)")
        run(c, f"grep -nE 'image:|NC_DB|container_name' {REMOTE}/docker-compose.yml")

        # 1) Check corrupt lower links for broken container layer
        run(
            c,
            "L=/var/lib/docker/overlay2/45c6e5682bbd5aaa21e107061bc71c7a24ec79b9a01603123028278d5b891d05; "
            "echo lower=; cat $L/lower 2>/dev/null; echo; "
            "for p in $(tr ':' ' ' < $L/lower 2>/dev/null); do "
            "  t=/var/lib/docker/overlay2/$p; "
            "  if [ -L \"$t\" ]; then "
            "    echo \"link $p -> $(readlink $t) exists=$(test -e $t && echo y || echo N)\"; "
            "  else echo \"MISSING_OR_BAD $p\"; fi; "
            "done",
            check=False,
        )

        # 2) Prefer mlnocodb:0.1.6 if present; else load from tarball; else keep 0.1.3 if runnable
        code, out, _ = run(
            c,
            "docker image inspect mlnocodb:0.1.6 >/dev/null 2>&1 && echo HAS_016 || echo NO_016; "
            "docker image inspect mlnocodb:0.1.3 >/dev/null 2>&1 && echo HAS_013 || echo NO_013; "
            "docker image inspect nginx:alpine >/dev/null 2>&1 && echo HAS_NGINX || echo NO_NGINX; "
            "docker image inspect node:22-slim >/dev/null 2>&1 && echo HAS_NODE || echo NO_NODE",
            check=False,
        )

        if "NO_016" in out and "HAS_013" not in out.split() or "NO_013" in out:
            # load 0.1.6 tarball if available
            run(
                c,
                f"test -s {REMOTE}/mlnocodb-0.1.6.tar.gz && "
                f"gunzip -c {REMOTE}/mlnocodb-0.1.6.tar.gz | docker load || true",
                timeout=900,
                check=False,
            )

        # If 0.1.6 exists, pin compose to it (matches prod); else keep 0.1.3
        code, out, _ = run(c, "docker image inspect mlnocodb:0.1.6 >/dev/null 2>&1 && echo HAS_016 || echo NO_016", check=False)
        if "HAS_016" in out:
            run(
                c,
                f"sed -i 's#image: *mlnocodb:[^[:space:]]*#image: mlnocodb:0.1.6#' {REMOTE}/docker-compose.yml; "
                f"grep -n 'image:' {REMOTE}/docker-compose.yml",
            )
            api_image = "mlnocodb:0.1.6"
        else:
            api_image = "mlnocodb:0.1.3"
            # verify 0.1.3 can create a throwaway container
            code, _, err = run(
                c,
                f"docker create --name mlnocodb-layer-probe {api_image} true && docker rm -f mlnocodb-layer-probe",
                check=False,
            )
            if code != 0:
                # try load 0.1.6 again or fail
                run(c, f"gunzip -c {REMOTE}/mlnocodb-0.1.6.tar.gz | docker load", timeout=900)
                run(
                    c,
                    f"sed -i 's#image: *mlnocodb:[^[:space:]]*#image: mlnocodb:0.1.6#' {REMOTE}/docker-compose.yml",
                )
                api_image = "mlnocodb:0.1.6"

        # Probe create from image (new RW layer, avoids corrupt container)
        run(
            c,
            f"docker rm -f mlnocodb-layer-probe 2>/dev/null; "
            f"docker create --name mlnocodb-layer-probe {api_image} true && "
            f"docker rm -f mlnocodb-layer-probe && echo IMAGE_LAYER_OK",
        )

        # Ensure nginx/node images exist
        run(
            c,
            "docker image inspect nginx:alpine >/dev/null 2>&1 || docker pull nginx:alpine; "
            "docker image inspect node:22-slim >/dev/null 2>&1 || docker pull node:22-slim",
            timeout=600,
            check=False,
        )

        # 3) Remove broken containers (keep images + named volumes / binds)
        run(
            c,
            "docker rm -f mlnocodb-api mlnocodb-nginx mlnocodb-ui 2>/dev/null; "
            "docker ps -a --filter name=mlnocodb --format '{{.ID}} {{.Names}} {{.Status}}'",
            check=False,
        )

        # 4) Recreate stack
        run(
            c,
            f"cd {REMOTE} && (docker compose up -d || docker-compose up -d)",
            timeout=180,
        )

        # 5) Health
        ok = False
        last = ""
        for i in range(40):
            _, last, _ = run(
                c,
                "docker ps --filter name=mlnocodb --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'; "
                "curl -sf -m 5 http://127.0.0.1:6080/api/v1/health && echo HEALTH_OK; "
                "curl -s -m 5 http://127.0.0.1:6080/api/v1/version; echo; "
                "curl -sf -m 5 -o /dev/null -w 'ui:%{http_code} nginx:%{http_code}\\n' "
                "http://127.0.0.1:6100/ http://127.0.0.1/ 2>/dev/null || "
                "curl -sf -m 5 -o /dev/null -w 'nginx:%{http_code}\\n' http://127.0.0.1/",
                check=False,
            )
            if "HEALTH_OK" in last or "0.301" in last:
                ok = True
                break
            time.sleep(3)
        if not ok:
            run(c, "docker logs --tail 80 mlnocodb-api 2>&1", check=False)
            raise SystemExit("health failed after recreate")

        run(
            c,
            "docker exec mlnocodb-api node -e \"require('mssql');console.log('mssql_ok')\" 2>/dev/null || "
            "echo mssql_check_skip; "
            "curl -s http://127.0.0.1:6080/api/v1/version; echo; "
            "curl -s http://127.0.0.1:6080/api/v1/health; echo",
            check=False,
        )
        print("REPAIR_OK", flush=True)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
