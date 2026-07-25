#!/usr/bin/env python3
"""Fix ModelXcMetaMssql prepare() to use BaseModelXcMeta render helpers."""
from pathlib import Path

p = Path(r"packages/nocodb/src/db/sql-mgr/code/models/xc/ModelXcMetaMssql.ts")
t = p.read_text(encoding="utf-8")
t = t.replace("this._renderXcColumns.bind(this)", "this.renderXcColumns.bind(this)")
t = t.replace("this._renderXcHasMany.bind(this)", "this.renderXcHasMany.bind(this)")
t = t.replace("this._renderXcBelongsTo.bind(this)", "this.renderXcBelongsTo.bind(this)")
# Remove obsolete private render helpers that shadow base (keep _getAbstractType)
# Leave _renderXc* methods — unused but harmless; or delete them later
p.write_text(t, encoding="utf-8")
print("fixed prepare bindings")
