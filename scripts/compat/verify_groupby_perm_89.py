#!/usr/bin/env python3
"""Verify MSSQL groupby for 报表权限组 on 100.89 after fix."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

BACKEND = os.environ.get("NC_BACKEND", "http://192.168.100.89:6080")
EMAIL = os.environ.get("NC_EMAIL", "mssql-ui-test@local.test")
PASS = os.environ.get("NC_PASS", "TestPass@12345")
TABLE = "mgk5a7qm92pzilb"
VIEW = "vwhyta7zpxmzmi6g"
BASE = "pw4yksn9i7x1fx4"
COL = "报表权限组"


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
            j = {"raw": raw[:2000]}
        return e.code, j


def main():
    code, j = req("POST", "/api/v1/auth/user/signin", {"email": EMAIL, "password": PASS})
    print("signin", code)
    token = j.get("token")
    if not token:
        print(j)
        raise SystemExit(2)

    q = urllib.parse.urlencode(
        {"column_name": COL, "limit": 25}
    )
    paths = [
        f"/api/v1/db/data/noco/{BASE}/{TABLE}/groupby?{q}",
        f"/api/v1/db/data/noco/{BASE}/{TABLE}/views/{VIEW}/groupby?{q}",
        f"/api/v1/db/data/noco/{BASE}/{TABLE}/groupby/count?{q}",
        f"/api/v1/db/data/noco/{BASE}/{TABLE}/views/{VIEW}/groupby/count?{q}",
    ]
    for p in paths:
        code, j = req("GET", p, token=token)
        print("GET", p.split("?")[0], "->", code)
        print(json.dumps(j, ensure_ascii=False)[:1200])
        if code >= 400:
            raise SystemExit(3)
    print("VERIFY_OK")


if __name__ == "__main__":
    main()
