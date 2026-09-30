#!/usr/bin/env python3
"""Probe source bkpov35slyra0jj tables for updated_at / CreatedTime meta on 100.93."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BACKEND = os.environ.get("NC_BACKEND", "http://192.168.100.93:6080")
EMAIL = "tongronghui@ml.com"
PASS = "Pass@w0rd"
SOURCE = "bkpov35slyra0jj"
BASE = "ptufhqjtqhuii6i"  # from URL /nc/<base>/...
TABLE = "m22hi1xblpkia3j"


def req(method, path, data=None, token=None):
    url = BACKEND + path
    body = None if data is None else json.dumps(data).encode()
    r = urllib.request.Request(url, data=body, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("xc-auth", token)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
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
    print("signin", code, list(j.keys()) if isinstance(j, dict) else j)
    token = j.get("token")
    if not token:
        raise SystemExit(2)

    # table meta
    code, meta = req("GET", f"/api/v2/meta/tables/{TABLE}", token=token)
    print("table", code, meta.get("title"), "source_id", meta.get("source_id"))
    for c in meta.get("columns") or []:
        if c.get("column_name") in ("updated_at", "created_at", "UpdatedAt", "CreatedAt") or c.get(
            "uidt"
        ) in ("CreatedTime", "LastModifiedTime", "CreatedBy", "LastModifiedBy"):
            print(
                json.dumps(
                    {
                        "id": c.get("id"),
                        "title": c.get("title"),
                        "column_name": c.get("column_name"),
                        "uidt": c.get("uidt"),
                        "dt": c.get("dt"),
                        "system": c.get("system"),
                        "cdf": c.get("cdf"),
                        "meta": c.get("meta"),
                        "pk": c.get("pk"),
                    },
                    ensure_ascii=False,
                )
            )

    # list tables in base, filter by source
    code, tables = req("GET", f"/api/v2/meta/bases/{BASE}/tables", token=token)
    print("tables_api", code, type(tables), (tables.keys() if isinstance(tables, dict) else None))
    lst = tables.get("list") if isinstance(tables, dict) else tables
    if not isinstance(lst, list):
        # try sources
        code, srcs = req("GET", f"/api/v2/meta/bases/{BASE}/sources", token=token)
        print("sources", code, json.dumps(srcs, ensure_ascii=False)[:800])
        code, src = req("GET", f"/api/v2/meta/bases/{BASE}/sources/{SOURCE}", token=token)
        print("source", code, json.dumps(src, ensure_ascii=False)[:800] if isinstance(src, dict) else src)
        return

    src_tables = [t for t in lst if t.get("source_id") == SOURCE]
    print(f"source {SOURCE} tables: {len(src_tables)} / total {len(lst)}")

    bad = []
    for t in src_tables:
        code, m = req("GET", f"/api/v2/meta/tables/{t['id']}", token=token)
        cols = m.get("columns") or []
        for c in cols:
            cn = (c.get("column_name") or "").lower()
            title = (c.get("title") or "").lower()
            uidt = c.get("uidt")
            if uidt in ("CreatedTime", "LastModifiedTime") or cn in (
                "updated_at",
                "created_at",
            ) or title in ("updated_at", "created_at", "updatedat", "createdat"):
                row = {
                    "table": t.get("title"),
                    "tid": t.get("id"),
                    "col": c.get("title"),
                    "cn": c.get("column_name"),
                    "uidt": uidt,
                    "system": c.get("system"),
                    "meta": c.get("meta"),
                }
                print(json.dumps(row, ensure_ascii=False))
                if uidt in ("CreatedTime", "LastModifiedTime") or c.get("system"):
                    bad.append(row)

    print("suspect_count", len(bad))


if __name__ == "__main__":
    main()
