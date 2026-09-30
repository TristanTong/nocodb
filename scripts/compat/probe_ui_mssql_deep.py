#!/usr/bin/env python3
"""Deep compare MSSQL presence in UI bundles + EE flag on 89/93."""
from __future__ import annotations

import os
import re
import paramiko

PWD89 = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")
PWD93 = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")


def run(host, pwd, cmd, timeout=120):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username="root", password=pwd, timeout=25)
    try:
        _, o, e = c.exec_command(cmd, timeout=timeout)
        out = o.read().decode("utf-8", "replace")
        err = e.read().decode("utf-8", "replace")
        return out, err
    finally:
        c.close()


def analyze(host, pwd, ui_dir, label):
    cmd = f"""
UIDIR={ui_dir}
echo "=== {label} nitro ==="
cat $UIDIR/nitro.json 2>/dev/null
echo
echo "=== isEeUI / ee ==="
grep -Rohl --include='*.js' --include='*.mjs' -E 'isEeUI|EEUI|ee:true' $UIDIR/public/_nuxt 2>/dev/null | head -5
# extract snippet around syncData.mssql
F=$(grep -Rl --include='*.js' 'objects.syncData.mssql' $UIDIR/public/_nuxt 2>/dev/null | head -1)
echo "file=$F"
if [ -n "$F" ]; then
  python - <<'PY'
import re,sys,glob,os
uidir=os.environ.get("UIDIR","")
# find from shell via file list
PY
  # use python on remote
  python -c "
import re, pathlib
p=pathlib.Path('$F')
t=p.read_text(encoding='utf-8', errors='replace')
for m in re.finditer(r'.{{0,80}}objects\\.syncData\\.mssql.{{0,120}}', t):
    print('CTX:', m.group(0)[:200])
    print('---')
# also ClientType mssql value
for pat in ['mssql','SQL Server','isAvailable:!0','isAvailable:true','isOssOnly']:
    print(pat, t.count(pat))
"
fi
echo "=== baseCreate SQL Server ==="
grep -Rohl --include='*.js' 'SQL Server' $UIDIR/public/_nuxt 2>/dev/null | head -3
python -c "
import pathlib,re
root=pathlib.Path('$UIDIR/public/_nuxt')
hits=0
for p in root.glob('*.js'):
  t=p.read_text(encoding='utf-8', errors='replace')
  if 'SQL Server' in t or 'objects.syncData.mssql' in t:
    hits+=1
    # around SQL Server
    i=t.find('SQL Server')
    if i>=0:
      print(p.name, 'SQL Server ctx:', t[max(0,i-60):i+80].replace(chr(10),' '))
    i=t.find('objects.syncData.mssql')
    if i>=0:
      print(p.name, 'mssql i18n ctx:', t[max(0,i-100):i+150].replace(chr(10),' '))
print('files_with_mssql_markers', hits)
"
echo "=== served homepage titles ==="
curl -s http://127.0.0.1/ | head -c 400; echo
curl -sI http://127.0.0.1/ | head -15
"""
    out, err = run(host, pwd, cmd, timeout=180)
    print(out)
    if err.strip():
        print("STDERR", err[-600:])


def main():
    analyze("192.168.100.93", PWD93, "/opt/mlnocodb/ui", "93")
    analyze("192.168.100.89", PWD89, "/opt/mlnocodb/ui-output", "89")


if __name__ == "__main__":
    main()
