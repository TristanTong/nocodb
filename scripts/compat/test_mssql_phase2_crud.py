#!/usr/bin/env python3
"""Delegate Phase 2 MSSQL CRUD acceptance to Node (knex+mssql).

Requires:
  NC_TEST_PASSWORD, NC_MSSQL_PASSWORD
  Backend on 6080 with MSSQL support loaded
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MJS = Path(__file__).resolve().parent / "test_mssql_phase2_crud.mjs"


def main() -> int:
    if not os.environ.get("NC_TEST_PASSWORD") or not os.environ.get(
        "NC_MSSQL_PASSWORD"
    ):
        print("Set NC_TEST_PASSWORD and NC_MSSQL_PASSWORD", file=sys.stderr)
        return 2
    return subprocess.call(["node", str(MJS)], cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
