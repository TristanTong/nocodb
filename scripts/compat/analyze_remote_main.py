#!/usr/bin/env python3
import re
from pathlib import Path

p = Path(r"C:\Users\ADMINI~1\AppData\Local\Temp\1\nocodb-main-10089.js")
s = p.read_text(encoding="utf-8", errors="ignore")
print("size", len(s))

hits = []
for m in re.finditer(r".{0,100}\.ai\b.{0,150}", s):
    t = m.group(0)
    if "delete" in t or "primaryKey" in t:
        hits.append((m.start(), t))
print("ai+delete/primaryKey hits", len(hits))
for i, (pos, t) in enumerate(hits[:40]):
    print(f"---{i} @{pos}---")
    print(t)

print("\n=== ai..delete (300) ===")
for i, m in enumerate(re.finditer(r".{0,60}\.ai.{0,300}?delete .{0,80}", s)):
    print(f"---{i}---")
    print(m.group(0)[:450])
    if i >= 15:
        break

print("\n=== undo near primaryKeys ===")
for i, m in enumerate(re.finditer(r".{0,40}undo.{0,200}primaryKeys.{0,200}", s)):
    print(f"---{i}---")
    print(m.group(0)[:450])
    if i >= 10:
        break

print("\n=== primaryKeys near .ai ===")
for i, m in enumerate(re.finditer(r"primaryKeys.{0,120}\.ai|primaryKeys\)\{if\([^)]+\.ai", s)):
    print(f"---{i}---")
    print(m.group(0)[:300])
    if i >= 10:
        break

# Also search for: for(... of this.model.primaryKeys)
print("\n=== for of primaryKeys ===")
for i, m in enumerate(re.finditer(r"for\([^)]*of this\.model\.primaryKeys[^)]*\).{0,250}", s)):
    print(f"---{i}---")
    print(m.group(0)[:400])
    if i >= 15:
        break
