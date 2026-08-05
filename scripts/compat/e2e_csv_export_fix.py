#!/usr/bin/env python3
"""E2E: create probe user, export CSV, poll /jobs/listen via nginx:80."""
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
    print(f"$ {cmd[:220]}")
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
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=os.environ["REMOTE_SSH_PASSWORD"], timeout=30)
    try:
        print("=== confirm /jobs/listen long-poll via nginx (expect hang ~8s then refresh/auth) ===")
        run(
            c,
            "curl -s -m 10 -o /tmp/jl.txt -w 'code=%{http_code} time=%{time_total}s ctype=%{content_type}\\n' "
            "-X POST http://127.0.0.1/jobs/listen -H 'Content-Type: application/json' "
            "-d '{\"_mid\":0,\"data\":{\"id\":\"nosuch\"}}'; echo BODY:; head -c 200 /tmp/jl.txt; echo",
            timeout=30,
        )

        hashed = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(10)).decode().replace("'", "''")
        sql = f"""
INSERT INTO nc_users_v2 (id, email, password, roles, token_version, created_at, updated_at)
SELECT 'usrprobeexport01', '{EMAIL}', '{hashed}', 'org-level-creator', '1', now(), now()
WHERE NOT EXISTS (SELECT 1 FROM nc_users_v2 WHERE email='{EMAIL}');
UPDATE nc_users_v2 SET password='{hashed}' WHERE email='{EMAIL}';
SELECT id, email, roles FROM nc_users_v2 WHERE email='{EMAIL}';
"""
        sftp = c.open_sftp()
        with sftp.file("/tmp/probe_user.sql", "w") as f:
            f.write(sql)
        # also get view owner / base membership to grant access
        grant = f"""
-- grant creator access to the base of the view
WITH v AS (
  SELECT base_id FROM nc_views_v2 WHERE id='{VIEW_ID}' LIMIT 1
), u AS (
  SELECT id FROM nc_users_v2 WHERE email='{EMAIL}' LIMIT 1
)
INSERT INTO nc_base_users_v2 (id, base_id, fk_user_id, roles, created_at, updated_at)
SELECT 'bu' || substr(md5(random()::text),1,12), v.base_id, u.id, 'creator', now(), now()
FROM v, u
WHERE NOT EXISTS (
  SELECT 1 FROM nc_base_users_v2 bu WHERE bu.base_id=v.base_id AND bu.fk_user_id=u.id
);
SELECT base_id FROM nc_views_v2 WHERE id='{VIEW_ID}';
"""
        with sftp.file("/tmp/probe_grant.sql", "w") as f:
            f.write(grant)
        sftp.close()

        print("\n=== upsert probe user + grant base ===")
        run(
            c,
            "docker run --rm --network mlnocodb_default -v /tmp/probe_user.sql:/tmp/probe_user.sql "
            "postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -f /tmp/probe_user.sql 2>&1",
        )
        run(
            c,
            "docker run --rm --network mlnocodb_default -v /tmp/probe_grant.sql:/tmp/probe_grant.sql "
            "postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -f /tmp/probe_grant.sql 2>&1",
        )

        print("\n=== signin ===")
        _, out, _ = run(
            c,
            "curl -s -m 15 -X POST http://127.0.0.1/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' "
            f"-d '{{\"email\":\"{EMAIL}\",\"password\":\"{PASSWORD}\"}}'",
        )
        token = json.loads(out).get("token")
        if not token:
            print("signin failed")
            return 1
        print(f"token_ok len={len(token)}")

        print("\n=== POST export via nginx ===")
        _, out, _ = run(
            c,
            f"curl -s -m 30 -X POST 'http://127.0.0.1/api/v2/export/{VIEW_ID}/csv' "
            f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' "
            f"-d '{{\"filenameTimeZone\":\"Asia/Shanghai\"}}'",
        )
        job = json.loads(out)
        job_id = job.get("id")
        print(f"job_id={job_id}")
        if not job_id:
            print("export create failed")
            return 1

        print("\n=== poll via nginx /jobs/listen ===")
        mid = 0
        final = None
        for i in range(8):
            _, out, _ = run(
                c,
                f"curl -s -m 35 -X POST 'http://127.0.0.1/jobs/listen' "
                f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' "
                f"-d '{{\"_mid\":{mid},\"data\":{{\"id\":\"{job_id}\"}}}}'",
                timeout=60,
            )
            print(f"poll[{i}] raw={out[:600]}")
            try:
                resp = json.loads(out)
            except Exception:
                continue
            items = resp if isinstance(resp, list) else [resp]
            for r in items:
                if isinstance(r, dict) and r.get("_mid"):
                    mid = max(mid, r["_mid"])
                if isinstance(r, dict) and r.get("status") == "update":
                    st = (r.get("data") or {}).get("status")
                    if st in ("completed", "failed"):
                        final = r
                        break
                if isinstance(r, dict) and r.get("status") == "close" and final:
                    break
            if final:
                break
            time.sleep(1)

        print("\n=== FINAL ===")
        print(json.dumps(final, ensure_ascii=False, indent=2)[:2000] if final else "NO_FINAL_STATUS")

        if final and (final.get("data") or {}).get("status") == "completed":
            url = ((final.get("data") or {}).get("data") or {}).get("result", {}).get("url")
            # structure might be data.data.result or data.result
            result = (final.get("data") or {}).get("result") or ((final.get("data") or {}).get("data") or {}).get("result")
            print("result=", result)
            if result and result.get("url"):
                u = result["url"]
                if not u.startswith("http"):
                    u = f"http://127.0.0.1/{u.lstrip('/')}"
                run(c, f"curl -s -m 20 -o /tmp/export_out.bin -w 'dl_code=%{{http_code}} size=%{{size_download}}\\n' '{u}'; file /tmp/export_out.bin; head -c 120 /tmp/export_out.bin; echo")

        print("\n=== api log snippet ===")
        run(c, "docker logs --tail 30 mlnocodb-api 2>&1 | grep -iE 'export|error|DataExport|completed|failed' | tail -20")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
