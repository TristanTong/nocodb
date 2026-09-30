#!/usr/bin/env python3
"""Diagnose group-by load error on 100.89 for 生产入库检验权限表."""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")
BASE = "pw4yksn9i7x1fx4"
TABLE = "mgk5a7qm92pzilb"
VIEW = "vwhyta7zpxmzmi6g"
BACKEND = "http://127.0.0.1:6080"

# Prefer existing test user if present
EMAIL = os.environ.get("NC_EMAIL", "mssql-ui-test@local.test")
PASS = os.environ.get("NC_PASS", "TestPass@12345")


def run(c, cmd, timeout=60):
    print(f"\n$ {cmd[:200]}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out[-5000:], flush=True)
    if err.strip() and code:
        print("ERR", err[-800:], flush=True)
    return code, out


def http_json(method, url, data=None, headers=None):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            j = json.loads(raw) if raw else {}
        except Exception:
            j = {"raw": raw}
        return e.code, j


def main():
    # Login via host (from this machine) — API may only be on 89
    # Use SSH to curl locally on 89 for reliability
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PWD, timeout=30)
    try:
        run(c, "docker ps --filter name=mlnocodb --format 'table {{.Names}}\\t{{.Status}}'")
        run(
            c,
            "docker logs --tail 80 mlnocodb-api 2>&1 | grep -iE 'error|group|stack|Exception|failed' | tail -40",
            timeout=30,
        )

        # auth + probe script on remote
        script = r"""
import json, urllib.request, urllib.error, sys

BACKEND = "http://127.0.0.1:6080"
EMAIL = %r
PASS = %r
BASE = %r
TABLE = %r
VIEW = %r

def req(method, path, data=None, token=None):
    url = BACKEND + path
    body = None if data is None else json.dumps(data).encode()
    r = urllib.request.Request(url, data=body, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("xc-auth", token)
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            j = json.loads(raw) if raw else {}
        except Exception:
            j = {"raw": raw[:2000]}
        return e.code, j

# login
code, j = req("POST", "/api/v1/auth/user/signin", {"email": EMAIL, "password": PASS})
print("signin", code, list(j.keys()) if isinstance(j, dict) else j)
token = j.get("token")
if not token:
    # try signup then signin
    req("POST", "/api/v1/auth/user/signup", {"email": EMAIL, "password": PASS})
    code, j = req("POST", "/api/v1/auth/user/signin", {"email": EMAIL, "password": PASS})
    print("signin2", code, j)
    token = j.get("token")
if not token:
    sys.exit(2)

# table meta
code, meta = req("GET", f"/api/v2/meta/tables/{TABLE}", token=token)
print("table_meta", code, "title=", meta.get("title"), "id=", meta.get("id"))
cols = meta.get("columns") or []
# find 报表权限组
hits = []
for col in cols:
    t = (col.get("title") or "") + " " + (col.get("column_name") or "")
    if "报表权限组" in t or "权限组" in t:
        hits.append(col)
print("permission_group_cols", json.dumps([{
  "id": c.get("id"), "title": c.get("title"), "column_name": c.get("column_name"),
  "uidt": c.get("uidt"), "dt": c.get("dt"), "cdf": c.get("cdf"),
  "pk": c.get("pk"), "rqd": c.get("rqd"), "system": c.get("system"),
  "colOptions": c.get("colOptions"), "meta": c.get("meta"),
} for c in hits], ensure_ascii=False, indent=2))

# also list all columns briefly
print("all_cols", json.dumps([
  {"id": c.get("id"), "title": c.get("title"), "uidt": c.get("uidt"), "dt": c.get("dt")}
  for c in cols
], ensure_ascii=False))

# view meta
code, view = req("GET", f"/api/v2/meta/views/{VIEW}", token=token)
print("view", code, "title=", view.get("title"), "type=", view.get("type"))
print("view_keys", sorted(view.keys()) if isinstance(view, dict) else view)

# list data without group
code, data = req("GET", f"/api/v2/tables/{TABLE}/records?limit=2", token=token)
print("list_ungrouped", code, "count", (data.get("pageInfo") or {}).get("totalRows"), "err", data.get("msg") or data.get("message"))
if isinstance(data, dict) and data.get("list"):
    print("sample_keys", list(data["list"][0].keys())[:20])

import urllib.parse

# try groupby API patterns used by UI
group_col = hits[0] if hits else None
if not group_col:
    print("NO group column found")
    sys.exit(3)

gid = group_col["id"]
gtitle = group_col["title"]
print("using", gid, gtitle, group_col.get("uidt"))

paths = [
    f"/api/v2/tables/{TABLE}/records/groupby?column_name={urllib.parse.quote(gtitle)}&limit=25",
    f"/api/v2/tables/{TABLE}/records/groupby?column_name={gid}&limit=25",
    f"/api/v2/tables/{TABLE}/groupby?column_name={urllib.parse.quote(gtitle)}",
]
for p in paths:
    code, j = req("GET", p, token=token)
    print("GET", p, "->", code)
    print(json.dumps(j, ensure_ascii=False)[:1500])

# also try with viewId
for p in [
    f"/api/v2/tables/{TABLE}/records/groupby?column_name={urllib.parse.quote(gtitle)}&viewId={VIEW}",
    f"/api/v2/tables/{TABLE}/records?viewId={VIEW}&limit=2",
]:
    code, j = req("GET", p, token=token)
    print("GET", p, "->", code)
    print(json.dumps(j, ensure_ascii=False)[:1500])
""" % (EMAIL, PASS, BASE, TABLE, VIEW)

        # write and run on remote
        sftp = c.open_sftp()
        with sftp.file("/tmp/diag_groupby_89.py", "w") as f:
            f.write(script)
        sftp.close()
        run(c, "python3 /tmp/diag_groupby_89.py 2>&1", timeout=120)

        # fresh api logs after request
        run(c, "docker logs --tail 100 mlnocodb-api 2>&1 | tail -60", timeout=30)
    finally:
        c.close()


if __name__ == "__main__":
    main()
