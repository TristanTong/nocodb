#!/usr/bin/env python3
"""Make probe user sign-inable and finish CSV export E2E via nginx."""
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
        print(err.rstrip()[:500])
    return code, out, err


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=os.environ["REMOTE_SSH_PASSWORD"], timeout=30)
    try:
        print("=== nc_users_v2 columns + sample admin ===")
        run(
            c,
            "docker run --rm --network mlnocodb_default postgres:15-alpine "
            "psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -c "
            "\"\\d nc_users_v2\" 2>&1 | head -60",
        )
        run(
            c,
            "docker run --rm --network mlnocodb_default postgres:15-alpine "
            "psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -c "
            "\"select column_name from information_schema.columns where table_name='nc_users_v2' order by 1\" 2>&1",
        )
        run(
            c,
            "docker run --rm --network mlnocodb_default postgres:15-alpine "
            "psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -c "
            "\"\\d nc_base_users_v2\" 2>&1 | head -40",
        )

        hashed = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(10)).decode().replace("'", "''")
        sql = f"""
-- unlock probe user for password login
UPDATE nc_users_v2 SET
  password='{hashed}',
  invite_token=NULL,
  invite_token_expires=NULL,
  email_verification_token=NULL,
  email_verified=true,
  blocked=false,
  roles=COALESCE(roles,'org-level-creator')
WHERE email='{EMAIL}';

-- base users schema may use different PK
INSERT INTO nc_base_users_v2 (base_id, fk_user_id, roles, created_at, updated_at)
SELECT 'phr43fj3yvo56qr', id, 'creator', now(), now()
FROM nc_users_v2 WHERE email='{EMAIL}'
AND NOT EXISTS (
  SELECT 1 FROM nc_base_users_v2 bu
  WHERE bu.base_id='phr43fj3yvo56qr' AND bu.fk_user_id=nc_users_v2.id
);

SELECT id,email,roles,email_verified,invite_token IS NULL AS no_invite, blocked
FROM nc_users_v2 WHERE email='{EMAIL}';
"""
        sftp = c.open_sftp()
        with sftp.file("/tmp/probe_fix.sql", "w") as f:
            f.write(sql)
        sftp.close()

        print("\n=== fix probe user ===")
        run(
            c,
            "docker run --rm --network mlnocodb_default -v /tmp/probe_fix.sql:/tmp/probe_fix.sql "
            "postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -f /tmp/probe_fix.sql 2>&1",
        )

        print("\n=== signin ===")
        _, out, _ = run(
            c,
            "curl -s -m 15 -X POST http://127.0.0.1/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' "
            f"-d '{{\"email\":\"{EMAIL}\",\"password\":\"{PASSWORD}\"}}'",
        )
        token = None
        try:
            token = json.loads(out).get("token")
        except Exception:
            pass
        if not token:
            print("signin still failing; dump user row")
            run(
                c,
                "docker run --rm --network mlnocodb_default postgres:15-alpine "
                "psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -c "
                f"\"select * from nc_users_v2 where email='{EMAIL}'\" 2>&1",
            )
            return 1

        print(f"token_ok len={len(token)}")

        print("\n=== export + poll ===")
        _, out, _ = run(
            c,
            f"curl -s -m 30 -X POST 'http://127.0.0.1/api/v2/export/{VIEW_ID}/csv' "
            f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' -d '{{\"filenameTimeZone\":\"Asia/Shanghai\"}}'",
        )
        job_id = json.loads(out).get("id")
        print("job=", out[:400])
        if not job_id:
            return 1

        mid = 0
        final = None
        for i in range(10):
            _, out, _ = run(
                c,
                f"curl -s -m 40 -X POST 'http://127.0.0.1/jobs/listen' "
                f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' "
                f"-d '{{\"_mid\":{mid},\"data\":{{\"id\":\"{job_id}\"}}}}'",
                timeout=60,
            )
            print(f"poll[{i}]={out[:700]}")
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
                # update payload embeds status at data.status
                st = data.get("status")
                if r.get("status") == "update" and st in ("completed", "failed"):
                    final = r
                    break
            if final:
                break

        print("\nFINAL:", json.dumps(final, ensure_ascii=False)[:1500] if final else None)
        if final:
            result = (final.get("data") or {}).get("result") or {}
            # sometimes nested
            if not result and isinstance((final.get("data") or {}).get("data"), dict):
                result = (final["data"]["data"].get("result") or {})
            url = result.get("url")
            print("download_url=", url)
            if url:
                if not url.startswith("http"):
                    url = "http://127.0.0.1/" + url.lstrip("/")
                run(c, f"curl -s -m 20 -o /tmp/export_out.bin -w 'dl=%{{http_code}} size=%{{size_download}}\\n' '{url}'; file /tmp/export_out.bin; head -c 200 /tmp/export_out.bin; echo")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
