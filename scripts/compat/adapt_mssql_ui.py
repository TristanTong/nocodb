#!/usr/bin/env python3
"""Adapt upstream MssqlUi to local SqlUi interface (no getMetaUIDataType)."""
from pathlib import Path
import re

src = Path(r"packages/nocodb-sdk/src/lib/sqlUi/MssqlUi.ts.upstream")
dst = Path(r"packages/nocodb-sdk/src/lib/sqlUi/MssqlUi.ts")
t = src.read_text(encoding="utf-8")

t = t.replace("import { abstractTypeToMetaUIType } from './metaUiDataType';\n", "")
t = re.sub(
    r"\n\s*// Introspection UIType[\s\S]*?static getMetaUIDataType\(col\): any \{\n\s*return abstractTypeToMetaUIType\(this\.getAbstractType\(col\)\);\n\s*\}\n",
    "\n",
    t,
)
t = re.sub(
    r"\n\s*getMetaUIDataType\(col: ColumnType\): UITypes \{\n\s*return MssqlUi\.getMetaUIDataType\(col\);\n\s*\}\n",
    "\n",
    t,
)
# Fix Partial without type arg used in upstream for older TS
t = t.replace(
    "static getCurrentDateDefault(col: Partial) {",
    "static getCurrentDateDefault(col: Partial<ColumnType>) {",
)
t = t.replace(
    "getCurrentDateDefault(_col: Partial) {",
    "getCurrentDateDefault(_col: Partial<ColumnType>) {",
)

dst.write_text(t, encoding="utf-8")
print("wrote", dst, "bytes", dst.stat().st_size)
print("getMetaUIDataType left:", "getMetaUIDataType" in t)
print("metaUiDataType left:", "metaUiDataType" in t)
