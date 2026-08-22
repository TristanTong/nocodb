# -*- coding: utf-8 -*-
"""Apply mlhr_add_candidate_created_by.sql"""
from __future__ import annotations

import os
import pathlib
import sys

import psycopg2

ROOT = pathlib.Path(__file__).resolve().parent
SQL = ROOT / "mlhr_add_candidate_created_by.sql"


def _load_env() -> None:
    for p in (
        pathlib.Path(r"D:\Project\workbuddyai\.env"),
        ROOT.parents[2] / "workbuddyai" / ".env",
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
    password = os.environ.get("MLHR_PG_PASSWORD", "")
    if not password:
        print("MLHR_PG_PASSWORD missing", file=sys.stderr)
        return 2
    conn = psycopg2.connect(
        host=os.environ.get("MLHR_PG_HOST", "192.168.100.89"),
        port=int(os.environ.get("MLHR_PG_PORT", "5432")),
        user=os.environ.get("MLHR_PG_USER", "postgres"),
        password=password,
        dbname=os.environ.get("MLHR_PG_DB", "mldata"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute(SQL.read_text(encoding="utf-8"))
            cur.execute(
                "SELECT COUNT(*) FROM mlhr.candidate WHERE created_by IS NOT NULL AND created_by<>''"
            )
            n = cur.fetchone()[0]
        conn.commit()
        print(f"OK candidate.created_by filled={n}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
