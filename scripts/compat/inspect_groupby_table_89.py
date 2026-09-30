#!/usr/bin/env python3
"""Inspect table columns + reproduce groupby SQL error detail on 89."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

import paramiko

BACKEND = "http://192.168.100.89:6080"
EMAIL = "mssql-ui-test@local.test"
PASS = "TestPass@12345"
TABLE = "mgk5a7qm92pzilb"


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
            j = json.loads(raw) if raw else {"raw": raw}
        except Exception:
            j = {"raw": raw[:3000]}
        return e.code, j


def main():
    _, j = req("POST", "/api/v1/auth/user/signin", {"email": EMAIL, "password": PASS})
    token = j["token"]
    _, meta = req("GET", f"/api/v2/meta/tables/{TABLE}", token=token)
    cols = meta.get("columns") or []
    print("title", meta.get("title"), "table_name", meta.get("table_name"))
    for c in cols:
        print(
            json.dumps(
                {
                    "title": c.get("title"),
                    "column_name": c.get("column_name"),
                    "uidt": c.get("uidt"),
                    "dt": c.get("dt"),
                    "pk": c.get("pk"),
                    "system": c.get("system"),
                    "ai": c.get("ai"),
                },
                ensure_ascii=False,
            )
        )

    # sample rows
    code, data = req("GET", f"/api/v2/tables/{TABLE}/records?limit=2", token=token)
    print("list", code, "total", (data.get("pageInfo") or {}).get("totalRows"))
    if data.get("list"):
        print("sample", json.dumps(data["list"][0], ensure_ascii=False)[:800])

    # trigger groupby then pull logs
    q = urllib.parse.urlencode({"column_name": "报表权限组", "limit": 5})
    req("GET", f"/api/v1/db/data/noco/pw4yksn9i7x1fx4/{TABLE}/groupby?{q}", token=token)

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "192.168.100.89",
        username="root",
        password=os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd"),
        timeout=25,
    )
    try:
        # ask tedious for fuller message if possible — dump last ERROR block
        _, o, _ = c.exec_command(
            "docker logs --tail 20 mlnocodb-api 2>&1",
            timeout=30,
        )
        print(o.read().decode("utf-8", "replace")[-4000:])
    finally:
        c.close()


if __name__ == "__main__":
    main()
