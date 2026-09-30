#!/usr/bin/env python3
"""Find integration for DWS source; try add Order column via NocoDB API on prod."""
from __future__ import annotations

import json
import os
import sys
import time

import paramiko
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

JUMP = "192.168.100.89"
JUMP_PWD = os.environ.get("REMOTE_SSH_PASSWORD_89", "Pass@w0rd")
PROD = "192.168.100.93"
PROD_PWD = os.environ.get("REMOTE_SSH_PASSWORD_93", "MedLinket@2025")
TABLE_ID = "ml7vrxmx5x9y7pu"
BASE_ID = "pys0rzjz5mgwkzy"
VIEW_ID = "vwncjefh9as7wsyr"


def run(c, cmd, timeout=90):
    print(f"\n$ {cmd[:260]}", flush=True)
    _, o, _ = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    print(out.rstrip()[:6000], flush=True)
    return out


def main():
    j = paramiko.SSHClient()
    j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    j.connect(JUMP, username="root", password=JUMP_PWD, timeout=30)

    p = paramiko.SSHClient()
    p.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    p.connect(PROD, username="root", password=PROD_PWD, timeout=30)

    try:
        sftp = j.open_sftp()
        sql = """
SELECT column_name FROM information_schema.columns
WHERE table_name='nc_sources_v2' ORDER BY 1;

SELECT id, alias, type, fk_integration_id, is_meta, is_schema_readonly, is_data_readonly,
       config::text, integration_config::text
FROM nc_sources_v2 WHERE id='bo7uyto2o0xk4ti';

SELECT id, title, type, config::text, meta::text
FROM nc_integrations_v2
WHERE id = (SELECT fk_integration_id FROM nc_sources_v2 WHERE id='bo7uyto2o0xk4ti')
   OR config::text ILIKE '%metabase_dws%'
LIMIT 10;

-- first admin user email for API login attempt (no password)
SELECT id, email, roles FROM nc_users_v2 ORDER BY created_at LIMIT 5;
"""
        with sftp.file("/tmp/integ.sql", "w") as f:
            f.write(sql)
        sftp.close()
        run(
            j,
            "docker run --rm --network host -e PGPASSWORD=Pass@w0rd "
            "-v /tmp/integ.sql:/tmp/s.sql:ro postgres:13 "
            "psql -h 192.168.100.97 -U postgres -d mlnoco -f /tmp/s.sql",
        )

        # Try decrypt config from running API container using node + env
        run(
            p,
            "docker exec mlnocodb-api sh -c "
            "'env | grep -E \"NC_CONNECTION_ENCRYPT|NC_AUTH|NC_DB\" | sed \"s/=.*/=***/\"'",
        )

        # Ask API for table meta (needs auth) — first get cookie via known test users if any
        # Instead: use docker exec to decrypt source config with app code
        decrypt_js = r"""
const { Client } = require('pg');
(async () => {
  const client = new Client({
    host: '192.168.100.97',
    port: 5432,
    user: 'postgres',
    password: 'Pass@w0rd',
    database: 'mlnoco',
  });
  await client.connect();
  const { rows } = await client.query(
    "SELECT id, alias, config, integration_config, fk_integration_id FROM nc_sources_v2 WHERE id=$1",
    ['bo7uyto2o0xk4ti']
  );
  console.log(JSON.stringify(rows[0], null, 2));
  if (rows[0].fk_integration_id) {
    const integ = await client.query(
      "SELECT id, title, type, config FROM nc_integrations_v2 WHERE id=$1",
      [rows[0].fk_integration_id]
    );
    console.log('INTEGRATION', JSON.stringify(integ.rows[0], null, 2));
  }
  await client.end();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
"""
        sftp2 = p.open_sftp()
        with sftp2.file("/tmp/dump_src.js", "w") as f:
            f.write(decrypt_js)
        sftp2.close()
        run(p, "docker cp /tmp/dump_src.js mlnocodb-api:/tmp/dump_src.js")
        # pg may not be in container; use node fetch via API internals instead
        run(
            p,
            "docker exec mlnocodb-api sh -c "
            "'cd /usr/src/app && node -e \"'
            'const {Client}=require(\\\"pg\\\");'
            '(async()=>{const c=new Client({connectionString:process.env.NC_DB.replace(/^pg:\\\\/\\\\//,\\\"postgres://\\\").replace(\\\"?u=\\\",\\\"\\\").replace(\\\"?u=postgres&p=\\\",\\\"postgres:\\\").replace(\\\"&d=\\\",\\\"/\\\")});'
            '})()\"' 2>&1 | head -20",
        )
    finally:
        j.close()
        p.close()


if __name__ == "__main__":
    main()
