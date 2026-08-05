#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, urllib.request, sys
sys.stdout.reconfigure(encoding='utf-8')
T=''
B='http://192.168.100.89'
def get(path):
 r=urllib.request.Request(B+path,headers={'xc-token':T,'Accept':'application/json'})
 with urllib.request.urlopen(r,timeout=30) as resp: return json.loads(resp.read().decode())
j=get('/api/v2/tables/mnk702c5j44og8b/records?limit=20')
rows=j.get('list') or []
print('cand', len(rows))
for f in ['status','grade','intent_level','job_family','job_title_cat','source_channel','education']:
 vals=sorted({str(r.get(f)) for r in rows if r.get(f) not in (None,'')})
 print(f, vals)
j2=get('/api/v2/tables/m0ixin184tfhckp/records?limit=20')
rows2=j2.get('list') or []
print('pool', len(rows2))
for f in ['pool_status','name_trust','source_channel','education']:
 vals=sorted({str(r.get(f)) for r in rows2 if r.get(f) not in (None,'')})
 print(f, vals)
