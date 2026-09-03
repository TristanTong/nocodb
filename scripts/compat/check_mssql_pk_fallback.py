#!/usr/bin/env python3
"""Assert MSSQL missing-PK fallback helper exists in MssqlClient."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
src = (
    ROOT / "packages/nocodb/src/db/sql-client/lib/mssql/MssqlClient.ts"
).read_text(encoding="utf-8")
assert "applyMissingPkFallback" in src
assert "code$/i" in src or "/code$/i" in src
print("MSSQL_PK_FALLBACK_OK")
