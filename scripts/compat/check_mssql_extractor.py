#!/usr/bin/env python3
"""Minimal check: MSSQL EREQUEST extractor maps Invalid object name."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
src = (ROOT / "packages/nocodb/src/helpers/db-error/mssql.extractor.ts").read_text(
    encoding="utf-8"
)
assert "class MssqlDBErrorExtractor" in src
assert "EREQUEST" in src
assert "Invalid object name" in src
ext = (ROOT / "packages/nocodb/src/helpers/db-error/extractor.ts").read_text(
    encoding="utf-8"
)
assert "MssqlDBErrorExtractor" in ext
assert "ClientType.MSSQL" in ext
assert re.search(r"EREQUEST", ext)
print("MSSQL_EXTRACTOR_OK")
sys.exit(0)
