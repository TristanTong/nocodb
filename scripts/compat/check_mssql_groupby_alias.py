#!/usr/bin/env python3
"""Assert MSSQL group-by uses expression not select alias (ponytail check)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "packages" / "nocodb" / "src" / "db" / "BaseModelSqlv2" / "group-by.ts"
text = SRC.read_text(encoding="utf-8")

assert "canGroupBySelectAlias" in text, "missing canGroupBySelectAlias"
assert "pushGroupBySelector" in text, "missing pushGroupBySelector"
assert "clientType() !== 'mssql'" in text, "missing mssql guard"
assert "CTE cannot be nested" in text or "rejects nested WITH" in text
# list/count default path must push expression for MSSQL
assert "expression: defaultColumnNameQb" in text or "expression: defaultExpr" in text
print("check_mssql_groupby_alias: OK")
