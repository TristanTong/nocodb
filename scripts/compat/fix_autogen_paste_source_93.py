#!/usr/bin/env python3
"""Audit + hide system Created/LastModified cols in views for source on 93;
smoke bulkUpdate with updated_at in payload after API patch."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BACKEND = os.environ.get("NC_BACKEND", "http://192.168.100.93:6080")
EMAIL = "tongronghui@ml.com"
PASS = "Pass@w0rd"
SOURCE = "bkpov35slyra0jj"
BASE = "ptufhqjtqhuii6i"
# Prefer admin for meta patch if editor lacks rights — try editor first
ADMIN_EMAIL = os.environ.get("NC_ADMIN_EMAIL", EMAIL)
ADMIN_PASS = os.environ.get("NC_ADMIN_PASS", PASS)


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


def signin(email, password):
    code, j = req("POST", "/api/v1/auth/user/signin", {"email": email, "password": password})
    if code != 200 or not j.get("token"):
        raise SystemExit(f"signin failed {email}: {code} {j}")
    return j["token"]


def main():
    token = signin(EMAIL, PASS)
    code, tables = req("GET", f"/api/v2/meta/bases/{BASE}/tables", token=token)
    lst = tables.get("list") or []
    src_tables = [t for t in lst if t.get("source_id") == SOURCE]
    print(f"tables in source {SOURCE}: {len(src_tables)}")

    report = []
    for t in src_tables:
        code, m = req("GET", f"/api/v2/meta/tables/{t['id']}", token=token)
        cols = m.get("columns") or []
        autogen = [
            c
            for c in cols
            if c.get("uidt")
            in ("CreatedTime", "LastModifiedTime", "CreatedBy", "LastModifiedBy")
        ]
        # views
        code, views = req("GET", f"/api/v2/meta/tables/{t['id']}/views", token=token)
        vlist = views.get("list") if isinstance(views, dict) else views
        shown = []
        for v in vlist or []:
            code, vc = req("GET", f"/api/v2/meta/views/{v['id']}/columns", token=token)
            vcols = vc.get("list") if isinstance(vc, dict) else vc
            for vc_item in vcols or []:
                col = next((c for c in cols if c["id"] == vc_item.get("fk_column_id")), None)
                if not col:
                    continue
                if col.get("uidt") in (
                    "CreatedTime",
                    "LastModifiedTime",
                    "CreatedBy",
                    "LastModifiedBy",
                ) and vc_item.get("show"):
                    shown.append(
                        {
                            "view": v.get("title"),
                            "vid": v.get("id"),
                            "col": col.get("title"),
                            "cid": col.get("id"),
                            "vcid": vc_item.get("id"),
                        }
                    )
                    # hide
                    code, _ = req(
                        "PATCH",
                        f"/api/v2/meta/views/{v['id']}/columns/{vc_item['id']}",
                        {"show": False},
                        token=token,
                    )
                    print(
                        f"hide {t.get('title')}/{v.get('title')}/{col.get('title')} -> {code}"
                    )
        report.append(
            {
                "table": t.get("title"),
                "tid": t.get("id"),
                "autogen": [
                    {"title": c.get("title"), "uidt": c.get("uidt"), "system": c.get("system")}
                    for c in autogen
                ],
                "was_shown": shown,
            }
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))

    # Smoke: bulk update with updated_at in payload on first table
    tid = src_tables[0]["id"]
    code, data = req("GET", f"/api/v2/tables/{tid}/records?limit=1", token=token)
    row = (data.get("list") or [None])[0]
    if not row:
        print("no rows to smoke")
        return
    pk = {"Id": row.get("Id"), "id": row.get("id")}
    pk = {k: v for k, v in pk.items() if v is not None}
    # pick a non-system text field to touch
    code, meta = req("GET", f"/api/v2/meta/tables/{tid}", token=token)
    editable = next(
        (
            c
            for c in meta.get("columns") or []
            if not c.get("system")
            and c.get("uidt") == "SingleLineText"
            and not c.get("pk")
        ),
        None,
    )
    payload = [{**pk, "updated_at": row.get("updated_at"), "created_at": row.get("created_at")}]
    if editable:
        payload[0][editable["title"]] = row.get(editable["title"])
    code, j = req(
        "PATCH",
        f"/api/v1/db/data/bulk/noco/{BASE}/{tid}",
        payload,
        token=token,
    )
    print("bulk_with_autogen", code, json.dumps(j, ensure_ascii=False)[:500])
    if code >= 400 and "auto generated" in json.dumps(j):
        raise SystemExit("STILL_FAILS_AUTOGEN")
    print("AUDIT_OK")


if __name__ == "__main__":
    main()
