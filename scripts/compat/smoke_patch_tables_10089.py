#!/usr/bin/env python3
"""Extra PATCH smoke: candidate + shipment tables via NocoDB API (nginx :80)."""
from __future__ import annotations

import json
import os
import urllib.request

HOST = "192.168.100.89"
TOKEN = os.environ.get("NC_TOKEN", "")
BASE = f"http://{HOST}"


def req(method: str, path: str, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"xc-token": TOKEN, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")[:300]
    except Exception as e:
        body_b = b""
        if hasattr(e, "read"):
            try:
                body_b = e.read()
            except Exception:
                pass
        return getattr(e, "code", None), f"{e} {body_b[:200]!r}"


def main():
    # list one candidate
    code, raw = req("GET", "/api/v2/tables/mnk702c5j44og8b/records?limit=1")
    print("GET candidate", code, raw[:200])
    j = json.loads(raw) if code == 200 else {}
    rows = j.get("list") or []
    if rows:
        cid = rows[0]["id"]
        old = rows[0].get("name")
        new = (old or "测") + "-api"
        code, raw = req("PATCH", "/api/v2/tables/mnk702c5j44og8b/records", [{"id": cid, "name": new}])
        print("PATCH candidate", code, raw)
        code, raw = req("GET", f"/api/v2/tables/mnk702c5j44og8b/records/{cid}")
        print("GET candidate after", code, raw[:200])
        # restore
        req("PATCH", "/api/v2/tables/mnk702c5j44og8b/records", [{"id": cid, "name": old}])

    # raw_resume already verified; quick confirm via :80
    code, raw = req(
        "PATCH",
        "/api/v2/tables/m0ixin184tfhckp/records",
        [{"id": 36, "original_name": "林晓明"}],
    )
    print("PATCH raw_resume", code, raw)


if __name__ == "__main__":
    main()
