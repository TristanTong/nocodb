#!/usr/bin/env python3
"""Download the completed export file via nginx /dltemp/."""
import json
import os
import urllib.parse

import paramiko

HOST = "192.168.100.93"
EMAIL = "csv-export-probe@local.test"
PASSWORD = "ProbePass@12345"
VIEW_ID = "vwfdauan1nf2yh6c"


def run(c, cmd, timeout=90):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    print(f"$ {cmd[:200]}\n{out.rstrip()[:2000]}")
    if err.strip() and code != 0:
        print(err[:300])
    return out


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=os.environ["REMOTE_SSH_PASSWORD"], timeout=30)
    try:
        out = run(
            c,
            "curl -s -m 15 -X POST http://127.0.0.1/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' "
            f"-d '{{\"email\":\"{EMAIL}\",\"password\":\"{PASSWORD}\"}}'",
        )
        token = json.loads(out).get("token")
        out = run(
            c,
            f"curl -s -m 30 -X POST 'http://127.0.0.1/api/v2/export/{VIEW_ID}/csv' "
            f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' -d '{{}}'",
        )
        job_id = json.loads(out)["id"]
        out = run(
            c,
            f"curl -s -m 40 -X POST 'http://127.0.0.1/jobs/listen' "
            f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' "
            f"-d '{{\"_mid\":0,\"data\":{{\"id\":\"{job_id}\"}}}}'",
            timeout=60,
        )
        resp = json.loads(out)
        items = resp if isinstance(resp, list) else [resp]
        url = None
        for r in items:
            try:
                url = r["data"]["data"]["result"]["url"]
            except Exception:
                pass
            if r.get("status") == "update" and (r.get("data") or {}).get("status") == "completed":
                url = ((r.get("data") or {}).get("data") or {}).get("result", {}).get("url") or url
        print("raw_url=", url)
        if not url:
            # second poll
            out = run(
                c,
                f"curl -s -m 40 -X POST 'http://127.0.0.1/jobs/listen' "
                f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' "
                f"-d '{{\"_mid\":1,\"data\":{{\"id\":\"{job_id}\"}}}}'",
                timeout=60,
            )
            resp = json.loads(out)
            for r in (resp if isinstance(resp, list) else [resp]):
                if (r.get("data") or {}).get("status") == "completed":
                    url = ((r.get("data") or {}).get("data") or {}).get("result", {}).get("url")
        # URL-encode path carefully (Chinese filename)
        # Use curl --path-as-is with encoded segments
        # Easiest: python urllib quote each segment
        parts = url.split("/")
        enc = "/".join(urllib.parse.quote(p, safe="") if i >= 0 else p for i, p in enumerate(parts))
        # Actually quote only non-ascii parts; keep slashes
        enc = "/".join(urllib.parse.quote(p, safe="") for p in parts)
        full = f"http://127.0.0.1/{enc}"
        print("full=", full)
        run(
            c,
            f"curl -s -m 20 -g -o /tmp/export_out.bin -w 'dl=%{{http_code}} size=%{{size_download}}\\n' '{full}'; "
            f"file /tmp/export_out.bin; head -c 200 /tmp/export_out.bin; echo",
        )
        # also via 6080 for comparison
        full2 = f"http://127.0.0.1:6080/{enc}"
        run(
            c,
            f"curl -s -m 20 -g -o /tmp/export_out2.bin -w 'api_dl=%{{http_code}} size=%{{size_download}}\\n' '{full2}'",
        )
    finally:
        c.close()


if __name__ == "__main__":
    main()
