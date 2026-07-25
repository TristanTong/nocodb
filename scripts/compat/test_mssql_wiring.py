#!/usr/bin/env python3
"""MSSQL wiring smoke checks (no live SQL Server required for unit part)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def check_files() -> list[tuple[str, bool, str]]:
    checks = []
    paths = [
        ROOT / "packages/nocodb-sdk/src/lib/sqlUi/MssqlUi.ts",
        ROOT / "packages/nocodb/src/db/sql-client/lib/mssql/MssqlClient.ts",
        ROOT / "packages/nocodb/src/db/sql-client/lib/mssql/mssql.queries.ts",
        ROOT / "packages/nocodb/src/db/sql-mgr/code/models/xc/ModelXcMetaMssql.ts",
    ]
    for p in paths:
        checks.append((f"exists:{p.name}", p.exists(), str(p)))

    enums = (ROOT / "packages/nocodb-sdk/src/lib/enums.ts").read_text(encoding="utf-8")
    checks.append(("ClientType.MSSQL", "MSSQL = 'mssql'" in enums, "enums.ts"))

    factory = (ROOT / "packages/nocodb/src/db/sql-client/lib/SqlClientFactory.ts").read_text(
        encoding="utf-8"
    )
    checks.append(("SqlClientFactory mssql", "MssqlClient" in factory and "mssql" in factory, "factory"))

    pkg = json.loads((ROOT / "packages/nocodb/package.json").read_text(encoding="utf-8"))
    checks.append(("dep:mssql", "mssql" in pkg.get("dependencies", {}), "package.json"))

    gui = (ROOT / "packages/nc-gui/utils/baseCreateUtils.ts").read_text(encoding="utf-8")
    checks.append(("UI clientTypes MSSQL", "ClientType.MSSQL" in gui and "SQL Server" in gui, "baseCreateUtils"))
    return checks


def try_live_mssql() -> tuple[str, str]:
    host = os.environ.get("NC_MSSQL_HOST")
    if not host:
        return "skip", "set NC_MSSQL_HOST/USER/PASSWORD/DB to run live test"

    user = os.environ.get("NC_MSSQL_USER", "sa")
    password = os.environ.get("NC_MSSQL_PASSWORD", "")
    database = os.environ.get("NC_MSSQL_DB", "master")
    port = os.environ.get("NC_MSSQL_PORT", "1433")
    # TC-MSSQL-01/02/03: connect, list schemas/tables, sample one table
    script = f"""
const sql = require('mssql');
(async () => {{
  await sql.connect({{
    user: {json.dumps(user)},
    password: {json.dumps(password)},
    server: {json.dumps(host)},
    port: {int(port)},
    database: {json.dumps(database)},
    options: {{ encrypt: false, trustServerCertificate: true }}
  }});
  const ok = await sql.query('SELECT 1 AS ok');
  const schemas = await sql.query(`
    SELECT TOP 20 TABLE_SCHEMA AS s, COUNT(*) AS c
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE='BASE TABLE'
    GROUP BY TABLE_SCHEMA
    ORDER BY c DESC`);
  const sample = await sql.query(`
    SELECT TOP 1 TABLE_SCHEMA AS s, TABLE_NAME AS t
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE='BASE TABLE'
    ORDER BY TABLE_SCHEMA, TABLE_NAME`);
  let sampleRows = [];
  if (sample.recordset.length) {{
    const s = sample.recordset[0].s;
    const t = sample.recordset[0].t;
    const q = 'SELECT TOP 5 * FROM [' + s + '].[' + t + ']';
    const r = await sql.query(q);
    sampleRows = {{ table: s + '.' + t, rows: r.recordset.length }};
  }}
  console.log(JSON.stringify({{
    ok: ok.recordset,
    schemas: schemas.recordset,
    sample: sampleRows
  }}));
  await sql.close();
}})().catch(e => {{ console.error(e.message); process.exit(1); }});
"""
    r = subprocess.run(
        ["node", "-e", script],
        cwd=str(ROOT / "packages/nocodb"),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        return "fail", (r.stderr or r.stdout)[:800]
    return "pass", (r.stdout or "").strip()[:800]


def main():
    results = check_files()
    failed = 0
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{status}] {name} — {detail}")

    live_status, live_detail = try_live_mssql()
    print(f"[{live_status.upper()}] live_mssql — {live_detail}")
    if live_status == "fail":
        failed += 1

    # node require check
    r = subprocess.run(
        [
            "node",
            "-e",
            "require('mssql'); console.log('mssql_ok')",
        ],
        cwd=str(ROOT / "packages/nocodb"),
        capture_output=True,
        text=True,
        timeout=20,
    )
    ok = r.returncode == 0 and "mssql_ok" in (r.stdout or "")
    print(f"[{'PASS' if ok else 'FAIL'}] require('mssql') — {(r.stderr or r.stdout)[:200]}")
    if not ok:
        failed += 1

    if failed:
        print(f"\nFAILED={failed}")
        raise SystemExit(1)
    print("\nALL_CHECKS_OK")


if __name__ == "__main__":
    main()
