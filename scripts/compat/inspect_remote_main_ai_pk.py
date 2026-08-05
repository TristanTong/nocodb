#!/usr/bin/env python3
"""Inspect remote main.js for AI-pk strip / batchUpdate patterns."""
from __future__ import annotations

import os
import paramiko

HOST = "192.168.100.89"
PWD = os.environ.get("REMOTE_SSH_PASSWORD", "Pass@w0rd")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="root", password=PWD, timeout=30, banner_timeout=60)

cmd = r'''docker exec mlnocodb-api python3 - <<'PY'
import re
p='/usr/src/app/docker/main.js'
s=open(p,'r',encoding='utf-8',errors='ignore').read()
print('size', len(s))
for pat in ['isInsertData','pkColumn.ai','Never write AI','prepareNocoData','batchUpdate','CASE "id"','primaryKeys']:
    print(pat, s.count(pat))
# find AI delete blocks
for m in re.finditer(r'.{0,120}\.ai.{0,80}delete.{0,80}', s):
    t=m.group(0)
    if 'primary' in t.lower() or 'pk' in t.lower() or 'ai' in t:
        print('---AI-DEL---')
        print(t[:400])
        if m.start()>5: break
# find prepareNocoData-ish
for m in re.finditer(r'prepareNocoData.{0,500}', s):
    print('---PREP---')
    print(m.group(0)[:500])
    break
for m in re.finditer(r'if\(!\w+\?\.undo\).{0,300}', s):
    if 'primaryKeys' in m.group(0) or '.ai' in m.group(0):
        print('---UNDO---')
        print(m.group(0)[:400])
# batchUpdate pks
for m in re.finditer(r'batchUpdate\(.{0,200}|const pks=\[\.\.\.new Set\(data\.map.{0,120}', s):
    print('---BATCH---')
    print(m.group(0)[:300])
    if m.start()>0 and 'pks' in m.group(0):
        break
# show around Undefined binding related CASE build
idx=s.find('CASE ')
print('first CASE idx', idx)
if idx>0:
    print(s[idx-200:idx+250])
PY'''

_, o, _ = c.exec_command(cmd, timeout=120, get_pty=True)
print(o.read().decode('utf-8','replace')[:8000])
c.close()
