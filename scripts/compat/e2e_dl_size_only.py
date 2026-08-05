#!/usr/bin/env python3
import json, os, urllib.parse, paramiko
HOST="192.168.100.93"
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="root", password=os.environ["REMOTE_SSH_PASSWORD"], timeout=30)
# reuse latest export file listing
_,o,_=c.exec_command("find /opt/mlnocodb/data -name '*.csv' 2>/dev/null | head -5; ls -la /usr/app/data 2>/dev/null; docker exec mlnocodb-api sh -c 'find /usr/app/data /tmp -name \"*.csv\" 2>/dev/null | head -10'")
print(o.read().decode("utf-8","replace"))
# quick download test with ASCII-only output
_,o,_=c.exec_command(
  "curl -s -m 15 -X POST http://127.0.0.1/api/v1/auth/user/signin -H 'Content-Type: application/json' "
  "-d '{\"email\":\"csv-export-probe@local.test\",\"password\":\"ProbePass@12345\"}'"
)
token=json.loads(o.read().decode())["token"]
_,o,_=c.exec_command(
  f"curl -s -m 30 -X POST http://127.0.0.1/api/v2/export/vwfdauan1nf2yh6c/csv -H 'Content-Type: application/json' -H 'xc-auth: {token}' -d '{{}}'"
)
job=json.loads(o.read().decode())["id"]
url=None
mid=0
for _ in range(8):
  _,o,_=c.exec_command(
    f"curl -s -m 40 -X POST http://127.0.0.1/jobs/listen -H 'Content-Type: application/json' -H 'xc-auth: {token}' "
    f"-d '{{\"_mid\":{mid},\"data\":{{\"id\":\"{job}\"}}}}'",
    timeout=60,
  )
  raw=o.read().decode("utf-8","replace")
  resp=json.loads(raw)
  for r in (resp if isinstance(resp,list) else [resp]):
    if r.get("_mid"): mid=max(mid,int(r["_mid"]))
    if (r.get("data") or {}).get("status")=="completed":
      url=((r.get("data") or {}).get("data") or {}).get("result",{}).get("url")
  if url: break
enc="/".join(urllib.parse.quote(p, safe="") for p in url.split("/"))
_,o,_=c.exec_command(f"curl -s -m 20 -g -o /tmp/export_out.bin -w '%{{http_code}} %{{size_download}}' 'http://127.0.0.1/{enc}'; echo; wc -c /tmp/export_out.bin; od -An -tx1 /tmp/export_out.bin | head -1")
print("DOWNLOAD:", o.read().decode("ascii","replace"))
c.close()
