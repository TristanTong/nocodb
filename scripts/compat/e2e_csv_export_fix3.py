#!/usr/bin/env python3
"""Fix probe user salt+password the NocoDB way; run CSV export E2E."""
import json
import os
import time

import bcrypt
import paramiko

HOST = "192.168.100.93"
VIEW_ID = "vwfdauan1nf2yh6c"
EMAIL = "csv-export-probe@local.test"
PASSWORD = "ProbePass@12345"


def run(c, cmd, timeout=120):
    print(f"$ {cmd[:240]}")
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip()[:2500])
    if err.strip() and code != 0:
        print(err.rstrip()[:400])
    return code, out, err


def main():
    # NocoDB: hashedPassword = bcrypt.hash(pass, salt); store both
    salt = bcrypt.gensalt(10).decode()
    hashed = bcrypt.hashpw(PASSWORD.encode(), salt.encode()).decode()
    salt_sql = salt.replace("'", "''")
    hash_sql = hashed.replace("'", "''")

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=os.environ["REMOTE_SSH_PASSWORD"], timeout=30)
    try:
        sql = f"""
UPDATE nc_users_v2 SET
  password='{hash_sql}',
  salt='{salt_sql}',
  invite_token=NULL,
  invite_token_expires=NULL,
  email_verification_token=NULL,
  email_verified=true,
  blocked=false
WHERE email='{EMAIL}';
SELECT email, salt IS NOT NULL AS has_salt, length(password) FROM nc_users_v2 WHERE email='{EMAIL}';
"""
        sftp = c.open_sftp()
        with sftp.file("/tmp/probe_salt.sql", "w") as f:
            f.write(sql)
        sftp.close()
        run(
            c,
            "docker run --rm --network mlnocodb_default -v /tmp/probe_salt.sql:/tmp/probe_salt.sql "
            "postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -f /tmp/probe_salt.sql 2>&1",
        )

        _, out, _ = run(
            c,
            "curl -s -m 15 -X POST http://127.0.0.1/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' "
            f"-d '{{\"email\":\"{EMAIL}\",\"password\":\"{PASSWORD}\"}}'",
        )
        token = json.loads(out).get("token")
        if not token:
            print("signin failed:", out)
            return 1
        print(f"token_ok len={len(token)}")

        _, out, _ = run(
            c,
            f"curl -s -m 30 -X POST 'http://127.0.0.1/api/v2/export/{VIEW_ID}/csv' "
            f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' -d '{{\"filenameTimeZone\":\"Asia/Shanghai\"}}'",
        )
        print("export:", out[:500])
        job_id = json.loads(out).get("id")
        if not job_id:
            return 1

        mid = 0
        final = None
        for i in range(12):
            _, out, _ = run(
                c,
                f"curl -s -m 40 -X POST 'http://127.0.0.1/jobs/listen' "
                f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' "
                f"-d '{{\"_mid\":{mid},\"data\":{{\"id\":\"{job_id}\"}}}}'",
                timeout=60,
            )
            print(f"poll[{i}]={out[:800]}")
            try:
                resp = json.loads(out)
            except Exception:
                continue
            for r in (resp if isinstance(resp, list) else [resp]):
                if not isinstance(r, dict):
                    continue
                if r.get("_mid"):
                    mid = max(mid, int(r["_mid"]))
                data = r.get("data") or {}
                if r.get("status") == "update" and data.get("status") in ("completed", "failed"):
                    final = r
                    break
            if final:
                break

        print("FINAL:", json.dumps(final, ensure_ascii=False)[:2000] if final else None)
        if not final:
            run(c, "docker logs --tail 40 mlnocodb-api 2>&1")
            return 1

        result = (final.get("data") or {}).get("result") or {}
        url = result.get("url")
        print("url=", url)
        if url:
            if not url.startswith("http"):
                url = "http://127.0.0.1/" + url.lstrip("/")
            run(
                c,
                f"curl -s -m 20 -o /tmp/export_out.bin -w 'dl=%{{http_code}} size=%{{size_download}}\\n' '{url}'; "
                f"file /tmp/export_out.bin; head -c 180 /tmp/export_out.bin; echo",
            )
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
