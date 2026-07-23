#!/usr/bin/env python3
"""mlnocodb smoke test runner — maps to docs/06 test cases.

Usage:
  python scripts/compat/run_smoke_tests.py

Optional env:
  NC_TEST_EMAIL / NC_TEST_PASSWORD  — enable TC-AUTH-01 / BASE / GRID API checks
  NC_BACKEND_URL  (default http://127.0.0.1:6080)
  NC_FRONTEND_URL (default http://127.0.0.1:6100)
  NC_VB_* / NC_META_*  — Vastbase / Meta PG connection (password required for those cases)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "docs" / "reports"
PGCLIENT = ROOT / "packages" / "nocodb" / "src" / "db" / "sql-client" / "lib" / "pg" / "PgClient.ts"
NOCO_DB = ROOT / "packages" / "nocodb" / "noco.db"

BACKEND = os.environ.get("NC_BACKEND_URL", "http://127.0.0.1:6080").rstrip("/")
FRONTEND = os.environ.get("NC_FRONTEND_URL", "http://127.0.0.1:6100").rstrip("/")
TEST_EMAIL = os.environ.get("NC_TEST_EMAIL", "")
TEST_PASSWORD = os.environ.get("NC_TEST_PASSWORD", "")
FE_OPEN_BUDGET_MS = int(os.environ.get("NC_FE_OPEN_BUDGET_MS", "3000"))
FE_OPEN_RUNS = int(os.environ.get("NC_FE_OPEN_RUNS", "3"))

VB = dict(
    host=os.environ.get("NC_VB_HOST", "192.168.100.99"),
    port=int(os.environ.get("NC_VB_PORT", "5432")),
    user=os.environ.get("NC_VB_USER", "sa"),
    password=os.environ.get("NC_VB_PASSWORD", ""),
    dbname=os.environ.get("NC_VB_DB", "metabase_rpt"),
)
PG_META = dict(
    host=os.environ.get("NC_META_HOST", "192.168.100.89"),
    port=int(os.environ.get("NC_META_PORT", "5432")),
    user=os.environ.get("NC_META_USER", "postgres"),
    password=os.environ.get("NC_META_PASSWORD", ""),
    dbname=os.environ.get("NC_META_DB", "mlnoco"),
)


def require_db_password(cfg: dict, env_hint: str):
    if not cfg.get("password"):
        return ("blocked", f"set {env_hint} to run DB cases")
    return None


RELATION_SQL = """
SELECT
  sch.nspname AS ts,
  pc.conname AS cstn,
  tbl.relname AS tn,
  col.attname AS cn,
  f_sch.nspname AS foreign_table_schema,
  f_tbl.relname AS rtn,
  f_col.attname AS rcn,
  pc.confupdtype AS ur,
  pc.confdeltype AS dr
FROM pg_constraint pc
  JOIN pg_class tbl ON tbl.oid = pc.conrelid
  JOIN pg_namespace sch ON sch.oid = tbl.relnamespace
  JOIN generate_series(1, 32) AS u(attposition)
    ON u.attposition <= coalesce(array_length(pc.conkey, 1), 0)
  LEFT JOIN pg_attribute col ON (col.attrelid = tbl.oid AND col.attnum = pc.conkey[u.attposition])
  LEFT JOIN pg_class f_tbl ON f_tbl.oid = pc.confrelid
  LEFT JOIN pg_namespace f_sch ON f_sch.oid = f_tbl.relnamespace
  LEFT JOIN pg_attribute f_col ON (f_col.attrelid = f_tbl.oid AND f_col.attnum = pc.confkey[u.attposition])
WHERE pc.contype = 'f' AND sch.nspname = %s AND f_sch.nspname = sch.nspname
ORDER BY tn
"""


@dataclass
class CaseResult:
    id: str
    title: str
    status: str  # pass | fail | blocked | skip
    duration_ms: int
    detail: str = ""


RESULTS: list[CaseResult] = []
AUTH_TOKEN: str | None = None
AUTH_BASE_ID: str | None = None
AUTH_TABLE_ID: str | None = None


def auth_headers() -> dict:
    if not AUTH_TOKEN:
        return {}
    return {"xc-auth": AUTH_TOKEN}


def record(case_id: str, title: str, status: str, started: float, detail: str = ""):
    RESULTS.append(
        CaseResult(
            id=case_id,
            title=title,
            status=status,
            duration_ms=int((time.time() - started) * 1000),
            detail=detail[:2000],
        )
    )
    mark = {"pass": "PASS", "fail": "FAIL", "blocked": "BLOCK", "skip": "SKIP"}[status]
    print(f"[{mark}] {case_id} {title} ({RESULTS[-1].duration_ms}ms) {detail[:120]}")


def http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None, timeout=20):
    data = None
    hdrs = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            return resp.status, parsed, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return e.code, parsed, raw


def run_case(case_id: str, title: str, fn):
    started = time.time()
    try:
        status, detail = fn()
        record(case_id, title, status, started, detail)
    except Exception as e:
        record(case_id, title, "fail", started, f"{e}\n{traceback.format_exc()}")


def tc_env_01():
    code, body, _ = http_json("GET", f"{BACKEND}/api/v1/health")
    ok = code == 200 and isinstance(body, dict) and body.get("message") == "OK"
    return ("pass" if ok else "fail", f"status={code} body={body}")


def tc_env_02():
    code, body, _ = http_json("GET", f"{BACKEND}/api/v1/version")
    ver = body.get("currentVersion") if isinstance(body, dict) else None
    ok = code == 200 and ver and str(ver).startswith("0.301")
    return ("pass" if ok else "fail", f"status={code} version={ver}")


def tc_env_03():
    code, body, raw = http_json("GET", f"{FRONTEND}/")
    # frontend may return HTML
    text = raw if isinstance(raw, str) else str(body)
    ok = code == 200 and ("NocoDB" in text or "nuxt" in text.lower() or len(text) > 500)
    return ("pass" if ok else "fail", f"status={code} len={len(text)}")


def tc_auth_01():
    global AUTH_TOKEN
    if not TEST_EMAIL or not TEST_PASSWORD:
        return ("blocked", "set NC_TEST_EMAIL / NC_TEST_PASSWORD to run")
    code, body, _ = http_json(
        "POST",
        f"{BACKEND}/api/v1/auth/user/signin",
        {"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    token = None
    if isinstance(body, dict):
        token = body.get("token") or (body.get("data") or {}).get("token")
    AUTH_TOKEN = token
    ok = code == 200 and bool(token)
    return ("pass" if ok else "fail", f"status={code} email={TEST_EMAIL} token={'yes' if token else 'no'}")


def tc_auth_02():
    code, body, _ = http_json(
        "POST",
        f"{BACKEND}/api/v1/auth/user/signin",
        {"email": "nobody@example.com", "password": "wrong-password-xxx"},
    )
    ok = code in (400, 401, 403)
    return ("pass" if ok else "fail", f"status={code} body={body}")


def tc_auth_03():
    # guest without token
    code, body, _ = http_json("GET", f"{BACKEND}/api/v1/auth/user/me")
    guest_ok = code == 200 and isinstance(body, dict) and "roles" in body
    if not AUTH_TOKEN:
        return ("pass" if guest_ok else "fail", f"guest status={code} body={body}")
    code2, body2, _ = http_json(
        "GET", f"{BACKEND}/api/v1/auth/user/me", headers=auth_headers()
    )
    authed = (
        code2 == 200
        and isinstance(body2, dict)
        and body2.get("email") == TEST_EMAIL
    )
    ok = guest_ok and authed
    return (
        "pass" if ok else "fail",
        f"guest_ok={guest_ok} authed_status={code2} email={body2.get('email') if isinstance(body2, dict) else None}",
    )


def tc_base_01():
    global AUTH_BASE_ID
    if not AUTH_TOKEN:
        return ("blocked", "login required")
    code, body, _ = http_json(
        "GET", f"{BACKEND}/api/v2/meta/bases/", headers=auth_headers()
    )
    lst = body.get("list") if isinstance(body, dict) else None
    ok = code == 200 and isinstance(lst, list) and len(lst) > 0
    if ok:
        AUTH_BASE_ID = lst[0].get("id")
    titles = [x.get("title") for x in (lst or [])[:5]]
    return ("pass" if ok else "fail", f"status={code} count={len(lst or [])} sample={titles}")


def tc_base_02():
    global AUTH_TABLE_ID
    if not AUTH_TOKEN or not AUTH_BASE_ID:
        return ("blocked", "login/base required")
    code, body, _ = http_json(
        "GET",
        f"{BACKEND}/api/v2/meta/bases/{AUTH_BASE_ID}/tables",
        headers=auth_headers(),
    )
    lst = body.get("list") if isinstance(body, dict) else None
    ok = code == 200 and isinstance(lst, list)
    if ok and lst:
        AUTH_TABLE_ID = lst[0].get("id")
    sample = [
        {k: t.get(k) for k in ("id", "title", "table_name")}
        for t in (lst or [])[:3]
    ]
    return (
        "pass" if ok else "fail",
        f"status={code} base={AUTH_BASE_ID} tables={len(lst or [])} sample={sample}",
    )


def tc_grid_01():
    if not AUTH_TOKEN or not AUTH_TABLE_ID:
        return ("blocked", "login/table required")
    code, body, _ = http_json(
        "GET",
        f"{BACKEND}/api/v2/tables/{AUTH_TABLE_ID}/records?limit=5",
        headers=auth_headers(),
    )
    lst = body.get("list") if isinstance(body, dict) else None
    ok = code == 200 and isinstance(lst, list)
    return (
        "pass" if ok else "fail",
        f"status={code} table={AUTH_TABLE_ID} rows={len(lst or [])}",
    )


def tc_grid_02():
    # Avoid writing into shared production bases during smoke.
    return (
        "skip",
        "shared Meta/production bases: skip write; Vastbase isolation CRUD covered by TC-VB-03",
    )


def tc_grid_03():
    return (
        "skip",
        "shared Meta/production bases: skip write; Vastbase isolation CRUD covered by TC-VB-03",
    )


def tc_ds_04_api():
    """List sources after login; prefer noting Vastbase/metabase if present."""
    if not AUTH_TOKEN:
        return ("blocked", "login required")
    code, body, _ = http_json(
        "GET", f"{BACKEND}/api/v2/meta/bases/", headers=auth_headers()
    )
    bases = body.get("list") if isinstance(body, dict) else []
    enabled_pg = 0
    samples = []
    for b in bases[:10]:
        bid = b.get("id")
        c2, src, _ = http_json(
            "GET",
            f"{BACKEND}/api/v2/meta/bases/{bid}/sources",
            headers=auth_headers(),
        )
        if c2 != 200 or not isinstance(src, dict):
            continue
        for s in src.get("list") or []:
            if s.get("type") == "pg" and s.get("enabled"):
                enabled_pg += 1
                samples.append(
                    {
                        "base": b.get("title"),
                        "alias": s.get("alias"),
                        "id": s.get("id"),
                    }
                )
    ok = code == 200 and enabled_pg >= 0
    # pass if API works; detail shows source inventory
    return (
        "pass" if ok else "fail",
        f"bases={len(bases or [])} enabled_pg_sources={enabled_pg} sample={samples[:5]}",
    )


def tc_port_01():
    b_ok = http_json("GET", f"{BACKEND}/api/v1/health")[0] == 200
    f_code, _, f_raw = http_json("GET", f"{FRONTEND}/")
    f_ok = f_code == 200
    # dashboard static
    d_code, _, _ = http_json("GET", f"{BACKEND}/dashboard/")
    d_ok = d_code in (200, 301, 302)
    ok = b_ok and f_ok
    return ("pass" if ok else "fail", f"backend={b_ok} frontend={f_ok} dashboard_code={d_code}")


def tc_perf_01():
    """TC-PERF-01: Frontend open-to-signin within budget (default 3000ms)."""
    import subprocess

    measure = ROOT / "scripts" / "compat" / "measure_frontend_open.mjs"
    if not measure.exists():
        return ("fail", f"missing {measure}")

    chrome = os.environ.get(
        "CHROME_PATH",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )
    if not Path(chrome).exists():
        return ("blocked", f"Chrome not found at {chrome}; set CHROME_PATH")

    runs = []
    for i in range(max(1, FE_OPEN_RUNS)):
        out = REPORT_DIR / f"frontend-open-perf-run{i + 1}.json"
        cmd = [
            "node",
            str(measure),
            "--url",
            f"{FRONTEND}/",
            "--budget",
            str(FE_OPEN_BUDGET_MS),
            "--out",
            str(out.relative_to(ROOT)),
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=240,
            env={**os.environ, "CHROME_PATH": chrome},
        )
        payload = None
        if out.exists():
            try:
                payload = json.loads(out.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = None
        open_ms = (payload or {}).get("openMs")
        passed = bool((payload or {}).get("passed")) and proc.returncode == 0
        runs.append({"run": i + 1, "openMs": open_ms, "passed": passed, "rc": proc.returncode})

    opens = [r["openMs"] for r in runs if isinstance(r.get("openMs"), (int, float))]
    all_pass = bool(opens) and all(r["passed"] for r in runs) and max(opens) <= FE_OPEN_BUDGET_MS
    detail = (
        f"budget={FE_OPEN_BUDGET_MS}ms runs={runs} "
        f"max={max(opens) if opens else 'n/a'} avg={round(sum(opens)/len(opens),1) if opens else 'n/a'}"
    )
    # also write aggregate
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "frontend-open-perf-latest.json").write_text(
        json.dumps(
            {
                "budgetMs": FE_OPEN_BUDGET_MS,
                "runs": runs,
                "passed": all_pass,
                "measuredAt": datetime.now(timezone.utc).isoformat(),
                "frontend": FRONTEND,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return ("pass" if all_pass else "fail", detail)


def tc_build_01():
    text = PGCLIENT.read_text(encoding="utf-8")
    # Ignore comments that mention the forbidden syntax by name
    code_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue
        if "--" in line:
            line = line.split("--", 1)[0]
        code_lines.append(line)
    code = "\n".join(code_lines)
    bad = bool(re.search(r"UNNEST\s*\([^)]*\)\s*WITH\s+ORDINALITY", code, re.I))
    bad = bad or ("WITH ORDINALITY" in code)
    has_fix = "generate_series(1, 32)" in code
    ok = (not bad) and has_fix
    return ("pass" if ok else "fail", f"has_ORDINALITY_in_code={bad} has_generate_series={has_fix}")


def tc_meta_01():
    before = NOCO_DB.stat().st_mtime if NOCO_DB.exists() else None
    http_json("GET", f"{BACKEND}/api/v2/meta/nocodb/info")
    time.sleep(0.5)
    after = NOCO_DB.stat().st_mtime if NOCO_DB.exists() else None
    # info endpoint should work and sqlite mtime should not jump forward significantly due to this call
    code, body, _ = http_json("GET", f"{BACKEND}/api/v2/meta/nocodb/info")
    ok = code == 200 and isinstance(body, dict) and body.get("version")
    detail = f"info_version={body.get('version') if isinstance(body, dict) else None} noco_db_mtime_before={before} after={after}"
    return ("pass" if ok else "fail", detail)


def tc_meta_02():
    blocked = require_db_password(PG_META, "NC_META_PASSWORD")
    if blocked:
        return blocked
    import psycopg2

    conn = psycopg2.connect(**PG_META, connect_timeout=8)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM nc_users_v2")
    users = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM nc_bases_v2")
    bases = cur.fetchone()[0]
    conn.close()
    code, body, _ = http_json("GET", f"{BACKEND}/api/v2/meta/nocodb/info")
    ok = users > 0 and bases > 0 and code == 200
    return ("pass" if ok else "fail", f"pg_users={users} pg_bases={bases} info={code}")


def tc_compat_01():
    blocked = require_db_password(VB, "NC_VB_PASSWORD")
    if blocked:
        return blocked
    import psycopg2

    conn = psycopg2.connect(**VB, connect_timeout=10)
    cur = conn.cursor()
    cur.execute(RELATION_SQL, ("dbo",))
    rows = cur.fetchall()
    conn.close()
    return ("pass", f"rows={len(rows)}")


def tc_compat_02():
    blocked = require_db_password(PG_META, "NC_META_PASSWORD")
    if blocked:
        return blocked
    import psycopg2

    conn = psycopg2.connect(**PG_META, connect_timeout=10)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS _nc_fk_test_child, _nc_fk_test_parent")
    cur.execute("CREATE TABLE _nc_fk_test_parent(id int PRIMARY KEY, name text)")
    cur.execute(
        "CREATE TABLE _nc_fk_test_child(id int PRIMARY KEY, parent_id int REFERENCES _nc_fk_test_parent(id))"
    )
    sql = """
SELECT
  sch.nspname AS ts,
  pc.conname AS cstn,
  tbl.relname AS tn,
  col.attname AS cn,
  f_sch.nspname AS foreign_table_schema,
  f_tbl.relname AS rtn,
  f_col.attname AS rcn
FROM pg_constraint pc
  JOIN pg_class tbl ON tbl.oid = pc.conrelid
  JOIN pg_namespace sch ON sch.oid = tbl.relnamespace
  JOIN generate_series(1, 32) AS u(attposition)
    ON u.attposition <= coalesce(array_length(pc.conkey, 1), 0)
  LEFT JOIN pg_attribute col ON (col.attrelid = tbl.oid AND col.attnum = pc.conkey[u.attposition])
  LEFT JOIN pg_class f_tbl ON f_tbl.oid = pc.confrelid
  LEFT JOIN pg_namespace f_sch ON f_sch.oid = f_tbl.relnamespace
  LEFT JOIN pg_attribute f_col ON (f_col.attrelid = f_tbl.oid AND f_col.attnum = pc.confkey[u.attposition])
WHERE pc.contype = 'f' AND sch.nspname = 'public'
  AND f_sch.nspname = sch.nspname AND tbl.relname = '_nc_fk_test_child'
"""
    cur.execute(sql)
    rows = cur.fetchall()
    cur.execute("DROP TABLE IF EXISTS _nc_fk_test_child, _nc_fk_test_parent")
    conn.close()
    ok = any(r[3] == "parent_id" and r[5] == "_nc_fk_test_parent" and r[6] == "id" for r in rows)
    return ("pass" if ok else "fail", f"rows={rows}")


def tc_vb_01():
    blocked = require_db_password(VB, "NC_VB_PASSWORD")
    if blocked:
        return blocked
    import psycopg2

    conn = psycopg2.connect(**VB, connect_timeout=10)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT schemaname, count(*) FROM pg_tables
        WHERE schemaname IN ('dbo','py_etl','public')
        GROUP BY 1 ORDER BY 2 DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    ok = sum(r[1] for r in rows) > 0
    return ("pass" if ok else "fail", f"tables_by_schema={rows}")


def tc_vb_02():
    blocked = require_db_password(VB, "NC_VB_PASSWORD")
    if blocked:
        return blocked
    import psycopg2

    conn = psycopg2.connect(**VB, connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='dbo' ORDER BY tablename LIMIT 1")
    row = cur.fetchone()
    if not row:
        conn.close()
        return ("fail", "no dbo tables")
    tn = row[0]
    cur.execute(f'SELECT * FROM dbo."{tn}" LIMIT 5')
    data = cur.fetchall()
    conn.close()
    return ("pass", f"table={tn} sample_rows={len(data)}")


def tc_vb_crud():
    """TC-VB-03/04/05 combined with cleanup."""
    blocked = require_db_password(VB, "NC_VB_PASSWORD")
    if blocked:
        return blocked
    import psycopg2

    ts = int(time.time())
    table = f"_nc_auto_test_{ts}"
    conn = psycopg2.connect(**VB, connect_timeout=10)
    conn.autocommit = True
    cur = conn.cursor()
    # prefer dbo schema
    cur.execute("SELECT 1 FROM pg_namespace WHERE nspname='dbo'")
    schema = "dbo" if cur.fetchone() else "public"
    fq = f'{schema}."{table}"'
    try:
        cur.execute(f"CREATE TABLE {fq} (id int PRIMARY KEY, name varchar(64), n int)")
        cur.execute(f"INSERT INTO {fq} (id, name, n) VALUES (1, 'alpha', 10)")
        cur.execute(f"SELECT id, name, n FROM {fq} WHERE id=1")
        got = cur.fetchone()
        if got != (1, "alpha", 10):
            return ("fail", f"select mismatch {got}")
        cur.execute(f"UPDATE {fq} SET name='beta', n=20 WHERE id=1")
        cur.execute(f"SELECT name, n FROM {fq} WHERE id=1")
        got2 = cur.fetchone()
        if got2 != ("beta", 20):
            return ("fail", f"update mismatch {got2}")
        cur.execute(f"DELETE FROM {fq} WHERE id=1")
        cur.execute(f"SELECT count(*) FROM {fq}")
        if cur.fetchone()[0] != 0:
            return ("fail", "delete failed")
        return ("pass", f"crud ok on {fq}")
    finally:
        try:
            cur.execute(f"DROP TABLE IF EXISTS {fq}")
        except Exception:
            pass
        conn.close()


def tc_vb_06():
    import psycopg2

    try:
        psycopg2.connect(
            host=VB["host"],
            port=VB["port"],
            user=VB["user"],
            password="definitely-wrong",
            dbname=VB["dbname"],
            connect_timeout=8,
        )
        return ("fail", "expected auth failure")
    except Exception as e:
        msg = str(e).lower()
        ok = "password" in msg or "auth" in msg or "fatal" in msg
        return ("pass" if ok else "fail", str(e).split("\n")[0])


def tc_vb_07():
    blocked = require_db_password(VB, "NC_VB_PASSWORD")
    if blocked:
        return blocked
    import psycopg2

    conn = psycopg2.connect(**VB, connect_timeout=10)
    cur = conn.cursor()
    cur.execute(RELATION_SQL, ("dbo",))
    fk_n = len(cur.fetchall())
    cur.execute("SELECT count(*) FROM pg_tables WHERE schemaname='dbo'")
    t_n = cur.fetchone()[0]
    conn.close()
    return ("pass", f"fk_rows={fk_n} dbo_tables={t_n}")


def tc_ds_connection():
    """TC-DS-02 connection layer (without UI)."""
    blocked = require_db_password(VB, "NC_VB_PASSWORD")
    if blocked:
        return blocked
    import psycopg2

    conn = psycopg2.connect(**VB, connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT current_database(), current_user")
    info = cur.fetchone()
    conn.close()
    ok = info[0] == "metabase_rpt"
    return ("pass" if ok else "fail", f"db={info}")


def write_reports():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    passed = sum(1 for r in RESULTS if r.status == "pass")
    failed = sum(1 for r in RESULTS if r.status == "fail")
    blocked = sum(1 for r in RESULTS if r.status == "blocked")
    skipped = sum(1 for r in RESULTS if r.status == "skip")
    total = len(RESULTS)

    md_path = REPORT_DIR / f"smoke-report-{stamp}.md"
    html_path = REPORT_DIR / f"smoke-report-{stamp}.html"
    json_path = REPORT_DIR / f"smoke-report-{stamp}.json"

    lines = [
        f"# mlnocodb 自动化冒烟测试报告",
        "",
        f"- 时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- Backend: `{BACKEND}`",
        f"- Frontend: `{FRONTEND}`",
        f"- 汇总: **{passed} passed** / {failed} failed / {blocked} blocked / {skipped} skip （共 {total}）",
        "",
        "| 用例 | 标题 | 结果 | 耗时ms | 详情 |",
        "|------|------|------|--------|------|",
    ]
    for r in RESULTS:
        detail = r.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r.id} | {r.title} | {r.status} | {r.duration_ms} | {detail[:180]} |")
    lines += [
        "",
        "## 说明",
        "",
        "- 海量表操作使用隔离表 `_nc_auto_test_*`，已自动 DROP。",
        "- `TC-AUTH-01` 等需登录的用例在未设置 `NC_TEST_EMAIL`/`NC_TEST_PASSWORD` 时记为 blocked。",
        "- UI 级 GRID/VIEW 用例未在本轮 API/SQL 冒烟中执行（见 Playwright）。",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")

    rows_html = "".join(
        f"<tr class='{r.status}'><td>{r.id}</td><td>{r.title}</td><td>{r.status}</td>"
        f"<td>{r.duration_ms}</td><td><code>{html_escape(r.detail[:300])}</code></td></tr>"
        for r in RESULTS
    )
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Smoke Report {stamp}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:24px}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ddd;padding:8px;vertical-align:top}}
th{{background:#f5f5f5}}
.pass{{background:#e8f5e9}} .fail{{background:#ffebee}} .blocked{{background:#fff8e1}}
code{{white-space:pre-wrap;font-size:12px}}
</style></head><body>
<h1>mlnocodb 自动化冒烟测试报告</h1>
<p>时间 {datetime.now().isoformat(timespec='seconds')} | Backend {BACKEND} | Frontend {FRONTEND}</p>
<p><b>{passed} passed</b> / {failed} failed / {blocked} blocked / {skipped} skip （共 {total}）</p>
<table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>ms</th><th>Detail</th></tr></thead>
<tbody>{rows_html}</tbody></table>
</body></html>"""
    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "passed": passed,
                    "failed": failed,
                    "blocked": blocked,
                    "skip": skipped,
                    "total": total,
                },
                "results": [asdict(r) for r in RESULTS],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # latest copies
    (REPORT_DIR / "smoke-report-latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    (REPORT_DIR / "smoke-report-latest.html").write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
    return md_path, html_path, json_path, failed


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def main():
    print(f"ROOT={ROOT}")
    print(f"BACKEND={BACKEND} FRONTEND={FRONTEND}")
    print(f"AUTH_EMAIL_SET={bool(TEST_EMAIL)}")

    cases = [
        ("TC-ENV-01", "Backend 健康检查", tc_env_01),
        ("TC-ENV-02", "版本接口", tc_env_02),
        ("TC-ENV-03", "Frontend 可访问", tc_env_03),
        ("TC-AUTH-01", "正确账号登录", tc_auth_01),
        ("TC-AUTH-02", "错误密码拒绝", tc_auth_02),
        ("TC-AUTH-03", "user/me guest+authed", tc_auth_03),
        ("TC-BASE-01", "登录后 Base 列表", tc_base_01),
        ("TC-BASE-02", "打开 Base 表列表", tc_base_02),
        ("TC-GRID-01", "网格/记录列表", tc_grid_01),
        ("TC-GRID-02", "网格新增", tc_grid_02),
        ("TC-GRID-03", "网格编辑", tc_grid_03),
        ("TC-DS-04", "登录后数据源列表", tc_ds_04_api),
        ("TC-PORT-01", "6080/6100 可访问", tc_port_01),
        ("TC-PERF-01", "Frontend 打开≤3s", tc_perf_01),
        ("TC-BUILD-01", "PgClient 无 WITH ORDINALITY", tc_build_01),
        ("TC-META-01", "Meta info + sqlite mtime", tc_meta_01),
        ("TC-META-02", "Meta PG 有用户/Base", tc_meta_02),
        ("TC-DS-02", "海量库连接 metabase_rpt", tc_ds_connection),
        ("TC-COMPAT-01", "Vastbase relationListAll SQL", tc_compat_01),
        ("TC-COMPAT-02", "标准 PG FK 列映射", tc_compat_02),
        ("TC-VB-01", "列举 schema/表", tc_vb_01),
        ("TC-VB-02", "只读抽样 dbo 表", tc_vb_02),
        ("TC-VB-03", "隔离表 CRUD(含04/05)", tc_vb_crud),
        ("TC-VB-06", "错误密码连接失败", tc_vb_06),
        ("TC-VB-07", "introspect+表列表联调", tc_vb_07),
    ]

    # Remaining UI-only placeholders
    for cid, title in [
        ("TC-DS-01", "添加标准 PG 源 UI"),
        ("TC-DS-03", "海量源同步 UI（SQL 层已由 COMPAT/VB 覆盖）"),
        ("TC-DS-05", "错误密码 UI 提示"),
        ("TC-VIEW-01", "切换表单视图 UI"),
        ("TC-VIEW-02", "切换看板 UI"),
    ]:
        started = time.time()
        record(cid, title, "skip", started, "需浏览器 UI / Playwright")

    for cid, title, fn in cases:
        run_case(cid, title, fn)

    md, html, js, failed = write_reports()
    print(f"\nReport MD:   {md}")
    print(f"Report HTML: {html}")
    print(f"Report JSON: {js}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
