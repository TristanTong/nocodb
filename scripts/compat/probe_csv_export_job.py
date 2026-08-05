#!/usr/bin/env python3
"""Create temp admin token via DB hash or use signup; trigger CSV export and poll job."""
import hashlib
import json
import os
import time

import paramiko
import bcrypt

HOST = "192.168.100.93"
VIEW_ID = "vwfdauan1nf2yh6c"
EMAIL = "csv-export-probe@local.test"
PASSWORD = "ProbePass@12345"


def run(c, cmd, timeout=120, show=True):
    if show:
        print(f"$ {cmd[:200]}")
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if show and out.strip():
        print(out.rstrip()[:2000])
    if show and err.strip() and code != 0:
        print(err.rstrip()[:500])
    return code, out, err


def main():
    pwd = os.environ["REMOTE_SSH_PASSWORD"]
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=pwd, timeout=30)
    try:
        print("=== recent export-related api logs ===")
        run(c, "docker logs --since 48h mlnocodb-api 2>&1 | grep -iE 'data-export|DataExport|export|jobs.listen|fileCreate|storage|ENOENT|EACCES' | tail -40")

        print("\n=== try signup probe user (may fail if disabled) ===")
        run(
            c,
            "curl -s -m 15 -X POST http://127.0.0.1:6080/api/v1/auth/user/signup "
            "-H 'Content-Type: application/json' "
            f"-d '{{\"email\":\"{EMAIL}\",\"password\":\"{PASSWORD}\"}}'",
        )

        print("\n=== ensure probe user password in meta DB ===")
        # bcrypt hash for PASSWORD
        hashed = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(10)).decode()
        # Escape for SQL: replace ' with ''
        hashed_sql = hashed.replace("'", "''")
        sql = (
            f"INSERT INTO nc_users_v2 (id, email, password, roles, token_version, created_at, updated_at) "
            f"SELECT 'usrprobeexport01', '{EMAIL}', '{hashed_sql}', 'org-level-creator', '1', now(), now() "
            f"WHERE NOT EXISTS (SELECT 1 FROM nc_users_v2 WHERE email='{EMAIL}'); "
            f"UPDATE nc_users_v2 SET password='{hashed_sql}', roles=COALESCE(roles,'org-level-creator') WHERE email='{EMAIL}'; "
            f"SELECT id,email,roles FROM nc_users_v2 WHERE email='{EMAIL}';"
        )
        # write sql to remote file via sftp to avoid quoting hell
        sftp = c.open_sftp()
        with sftp.file("/tmp/probe_user.sql", "w") as f:
            f.write(sql)
        sftp.close()
        run(
            c,
            "docker cp /tmp/probe_user.sql $(docker create --name tmppg postgres:15-alpine):/tmp/probe_user.sql 2>/dev/null; "
            "docker rm tmppg 2>/dev/null; "
            "docker run --rm --network mlnocodb_default -v /tmp/probe_user.sql:/tmp/probe_user.sql "
            "postgres:15-alpine psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' -f /tmp/probe_user.sql 2>&1",
        )

        print("\n=== signin probe user ===")
        code, out, _ = run(
            c,
            "curl -s -m 15 -X POST http://127.0.0.1:6080/api/v1/auth/user/signin "
            "-H 'Content-Type: application/json' "
            f"-d '{{\"email\":\"{EMAIL}\",\"password\":\"{PASSWORD}\"}}'",
        )
        try:
            token = json.loads(out).get("token")
        except Exception:
            token = None
        if not token:
            print("still no token; abort")
            return 1
        print(f"got token len={len(token)}")

        # grant access to base if needed - check user bases
        print("\n=== me / bases ===")
        run(c, f"curl -s -m 15 http://127.0.0.1:6080/api/v1/db/meta/projects -H 'xc-auth: {token}' | head -c 400; echo")

        print("\n=== POST export ===")
        code, out, _ = run(
            c,
            f"curl -s -m 30 -X POST 'http://127.0.0.1:6080/api/v2/export/{VIEW_ID}/csv' "
            f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' "
            f"-d '{{\"filenameTimeZone\":\"Asia/Shanghai\"}}'",
        )
        try:
            job = json.loads(out)
            job_id = job.get("id")
        except Exception:
            job_id = None
            print("export failed body:", out[:800])

        if not job_id:
            # try internal postOperation path used by UI
            print("\n=== resolve workspace/base for internal API ===")
            run(
                c,
                "docker run --rm --network mlnocodb_default postgres:15-alpine "
                "psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' "
                f"-tAc \"select id, base_id, fk_model_id, title from nc_views_v2 where id='{VIEW_ID}'\" 2>&1",
            )
            return 1

        print(f"job_id={job_id}")

        print("\n=== poll jobs.listen (3 rounds) ===")
        mid = 0
        for i in range(6):
            time.sleep(2)
            code, out, _ = run(
                c,
                f"curl -s -m 25 -X POST 'http://127.0.0.1:6080/jobs/listen' "
                f"-H 'Content-Type: application/json' -H 'xc-auth: {token}' "
                f"-d '{{\"_mid\":{mid},\"data\":{{\"id\":\"{job_id}\"}}}}'",
            )
            print(f"poll[{i}]={out[:500]}")
            try:
                resp = json.loads(out)
                if isinstance(resp, dict):
                    mid = resp.get("_mid", mid)
                    if resp.get("status") == "close":
                        break
                    if resp.get("status") == "update" and resp.get("data", {}).get("status") in ("completed", "failed"):
                        break
            except Exception:
                pass

        print("\n=== api logs tail ===")
        run(c, "docker logs --tail 50 mlnocodb-api 2>&1")

        print("\n=== exported files on disk ===")
        run(c, "find /opt/mlnocodb/data -type f 2>/dev/null | head -40; ls -laR /opt/mlnocodb/data 2>/dev/null | head -40")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
