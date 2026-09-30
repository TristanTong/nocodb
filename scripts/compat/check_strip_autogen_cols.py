#!/usr/bin/env python3
"""Assert auto-generated cols are stripped (not thrown) on update/paste."""
from __future__ import annotations

from pathlib import Path

SRC = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "nocodb"
    / "src"
    / "db"
    / "BaseModelSqlv2.ts"
)
text = SRC.read_text(encoding="utf-8")
assert "is auto generated and cannot be updated" not in text, (
    "still throws auto-generated error — should strip instead"
)
assert "Ignore client-supplied auto-generated" in text or "visible system timestamp" in text
assert text.count("delete data[column.title]") + text.count("delete d[col.title]") >= 2
print("check_strip_autogen_cols: OK")
