#!/usr/bin/env python3
"""Hash password inside API container with bcryptjs; update user; restart api; export E2E."""
import json
import os
import time

import paramiko

HOST = "192.168.100.93"
VIEW_ID = "vwfdauan1nf2yh6c"
EMAIL = "csv-export-probe@local.test"
PASSWORD = "ProbePass@12345"


def run(c, cmd, timeout=120):
    print(f"$ {cmd[:260]}")
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip()[:2500])
    if err.strip() and code != 0:
        print(err.rstrip()[:500])
    return code, out, err


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=os.environ["REMOTE_SSH_PASSWORD"], timeout=30)
    try:
        # Generate salt+hash with same bcryptjs used by NocoDB inside container
        js = (
            "const bcrypt=require('bcryptjs');"
            f"const salt=bcrypt.genSaltSync(10);"
            f"const password=bcrypt.hashSync('{PASSWORD}', salt);"
            "console.log(JSON.stringify({salt,password}));"
        )
        _, out, _ = run(
            c,
            f"docker exec mlnocodb-api node -e \"{js}\"",
        )
        creds = json.loads(out.strip().splitlines()[-1])
        salt_sql = creds["salt"].replace("'", "''")
        hash_sql = creds["password"].replace("'", "''")

        sql = f"""
UPDATE nc_users_v2 SET password='{hash_sql}', salt='{salt_sql}',
  invite_token=NULL, invite_token_expires=NULL, email_verification_token=NULL,
  email_verified=true, blocked=false, is_deleted=false
WHERE email='{EMAIL}';
SELECT email, left(salt,10) as salt_prefix, left(password,10) as pw_prefix FROM nc_users_v2 WHERE email='{EMAIL}';
"""
        sftp = c.open_sftp()
        with sftp.file("/tmp/probe_bcryptjs.sql", "w") as f:
            f.write(sql)
        sftp.close()
        run(
            c,
            "docker run --rm --network mlnocodb_default -v /tmp/probe_bcryptjs.sql:/tmp/probe_bcryptjs.sql "
            "postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -f /tmp/probe_bcryptjs.sql 2>&1",
        )

        print("=== restart api to clear user cache ===")
        run(c, "docker restart mlnocodb-api")
        time.sleep(25)
        run(c, "docker ps --filter name=mlnocodb-api --format '{{.Status}}'")

        _, out, _ = run(
            c,
            "curl -s -m 15 -X POST http://127.0.0.1/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' "
            f"-d '{{\"email\":\"{EMAIL}\",\"password\":\"{PASSWORD}\"}}'",
        )
        token = json.loads(out).get("token") if out.strip().startswith("{") else None
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
            print(f"poll[{i}]={out[:900]}")
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
        if final:
            url = ((final.get("data") or {}).get("result") or {}).get("url")
            print("url=", url)
            if url:
                if not url.startswith("http"):
                    url = "http://127.0.0.1/" + url.lstrip("/")
                run(c, f"curl -s -m 20 -o /tmp/export_out.bin -w 'dl=%{{http_code}} size=%{{size_download}}\\n' '{url}'; file /tmp/export_out.bin; head -c 200 /tmp/export_out.bin; echo")
        else:
            run(c, "docker logs --tail 50 mlnocodb-api 2>&1")
            return 1
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
