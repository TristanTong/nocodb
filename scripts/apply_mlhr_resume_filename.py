# -*- coding: utf-8 -*-
"""Apply mlhr_add_resume_filename.sql to mldata (NocoDB 同源库)."""
from __future__ import annotations

import os
import pathlib
import sys

import psycopg2

ROOT = pathlib.Path(__file__).resolve().parent
SQL = ROOT / "mlhr_add_resume_filename.sql"


def _load_env() -> None:
    for p in (
        ROOT.parents[2] / "workbuddyai" / ".env",
        pathlib.Path(r"D:\Project\workbuddyai\.env"),
        pathlib.Path(".env"),
    ):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("[") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
        break


def main() -> int:
    _load_env()
    host = os.environ.get("MLHR_PG_HOST", "192.168.100.89")
    port = int(os.environ.get("MLHR_PG_PORT", "5432"))
    user = os.environ.get("MLHR_PG_USER", "postgres")
    password = os.environ.get("MLHR_PG_PASSWORD", "")
    dbname = os.environ.get("MLHR_PG_DB", "mldata")
    if not password:
        print("MLHR_PG_PASSWORD missing", file=sys.stderr)
        return 2
    sql = SQL.read_text(encoding="utf-8")
    conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM mlhr.raw_resume WHERE resume_filename IS NOT NULL AND resume_filename<>'') AS raw_filled,
                  (SELECT COUNT(*) FROM mlhr.candidate WHERE resume_filename IS NOT NULL AND resume_filename<>'') AS cand_filled
                """
            )
            row = cur.fetchone()
        conn.commit()
        print(f"OK resume_filename added; raw_filled={row[0]} cand_filled={row[1]}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
