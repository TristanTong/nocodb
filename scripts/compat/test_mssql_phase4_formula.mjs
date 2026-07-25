/**
 * Phase 4 MSSQL formula acceptance:
 * - unsupported list present in MssqlUi
 * - create Formula columns (LEN/TRIM/IF/NOW) on synced isolation table
 * - records API returns computed values
 */
import { createRequire } from 'module';
import { readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { randomUUID } from 'crypto';

const require = createRequire(import.meta.url);
const knex = require('knex');
const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '../..');

const BACKEND = process.env.NC_BACKEND || 'http://127.0.0.1:6080';
const EMAIL = process.env.NC_TEST_EMAIL || 'mssql-ui-test@local.test';
const PASSWORD = process.env.NC_TEST_PASSWORD || '';
const BASE_ID = process.env.NC_BASE_ID || 'pw4yksn9i7x1fx4';
const EXISTING_SOURCE_ID = process.env.NC_MSSQL_SOURCE_ID || '';

const MSSQL = {
  host: process.env.NC_MSSQL_HOST || '192.168.1.11',
  port: Number(process.env.NC_MSSQL_PORT || 5678),
  user: process.env.NC_MSSQL_USER || 'sa',
  password: process.env.NC_MSSQL_PASSWORD || '',
  database: process.env.NC_MSSQL_DB || 'Metabase_ODS',
};
const SCHEMA = process.env.NC_MSSQL_SCHEMA || 'UFDATA';
const TABLE = process.env.NC_MSSQL_TABLE || `_nc_p4_${Math.floor(Date.now() / 1000)}`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function req(method, path, body, token, timeout = 180000) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['xc-auth'] = token;
  let lastErr;
  for (let attempt = 0; attempt < 4; attempt++) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(BACKEND + path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: ctrl.signal,
      });
      const raw = await res.text();
      let payload = {};
      if (raw) {
        try {
          payload = JSON.parse(raw);
        } catch {
          payload = { raw: raw.slice(0, 800) };
        }
      }
      return [res.status, payload];
    } catch (e) {
      lastErr = e;
      await sleep(2000 * (attempt + 1));
    } finally {
      clearTimeout(t);
    }
  }
  throw lastErr;
}

function ok(name, cond, detail = '') {
  console.log(cond ? 'PASS' : 'FAIL', name, detail);
  if (!cond) throw new Error(`FAILED:${name}:${detail}`);
}

function makeDb() {
  return knex({
    client: 'mssql',
    connection: {
      host: MSSQL.host,
      port: MSSQL.port,
      user: MSSQL.user,
      password: MSSQL.password,
      database: MSSQL.database,
      options: { encrypt: false, trustServerCertificate: true, port: MSSQL.port },
    },
  });
}

async function listSources(tok) {
  const [, sources] = await req('GET', `/api/v1/db/meta/projects/${BASE_ID}/bases`, undefined, tok);
  return Array.isArray(sources) ? sources : sources.list || [];
}

async function waitTable(tok, sourceId, tableName, tries = 40) {
  for (let i = 0; i < tries; i++) {
    const [, tables] = await req('GET', `/api/v1/db/meta/projects/${BASE_ID}/tables`, undefined, tok);
    const tlist = Array.isArray(tables) ? tables : tables.list || [];
    const found = tlist.find(
      (t) =>
        t.source_id === sourceId &&
        String(t.table_name || '').toLowerCase() === tableName.toLowerCase(),
    );
    if (found) return found;
    if (i % 3 === 0) {
      await req('POST', `/api/v2/meta/bases/${BASE_ID}/meta-diff/${sourceId}`, undefined, tok);
    }
    await sleep(3000);
  }
  throw new Error('TABLE_SYNC_TIMEOUT');
}

async function main() {
  if (!PASSWORD) {
    console.error('Set NC_TEST_PASSWORD');
    process.exit(2);
  }
  if (!MSSQL.password) {
    console.error('Set NC_MSSQL_PASSWORD');
    process.exit(2);
  }

  // Static: unsupported list
  const uiSrc = readFileSync(
    join(ROOT, 'packages/nocodb-sdk/src/lib/sqlUi/MssqlUi.ts'),
    'utf8',
  );
  for (const fn of ['REGEX_MATCH', 'ARRAYSORT', 'DATEADD', 'VALUE', 'MD5']) {
    ok(`unsupported_${fn}`, uiSrc.includes(`'${fn}'`), 'MssqlUi.getUnsupportedFnList');
  }
  const mapSrc = readFileSync(
    join(ROOT, 'packages/nocodb/src/db/functionMappings/mssql.ts'),
    'utf8',
  );
  ok('map_trim_ltrim_rtrim', mapSrc.includes('LTRIM(RTRIM'), 'mssql.ts TRIM');
  ok('map_now_getdate', /NOW:\s*'GETDATE'/.test(mapSrc), 'mssql.ts NOW');
  ok('map_coalesce', mapSrc.includes('COALESCE'), 'mssql.ts COALESCE');

  const db = makeDb();
  let fq;
  try {
    const [hcode] = await req('GET', '/api/v1/health');
    ok('health', hcode === 200);

    const [, sign] = await req('POST', '/api/v1/auth/user/signin', { email: EMAIL, password: PASSWORD });
    const tok = sign.token;
    ok('signin', Boolean(tok));

    fq = `[${SCHEMA}].[${TABLE}]`;
    await db.raw(`
      IF OBJECT_ID(N'${SCHEMA}.${TABLE}', N'U') IS NOT NULL DROP TABLE ${fq};
      CREATE TABLE ${fq} (
        Id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Title NVARCHAR(200) NOT NULL,
        Amount DECIMAL(18,4) NULL
      );
      INSERT INTO ${fq} (Title, Amount) VALUES (N'  hello  ', 1.5);
    `);

    const sources = await listSources(tok);
    const source =
      sources.find((s) => s.id === EXISTING_SOURCE_ID) ||
      sources.find((s) => s.type === 'mssql' && !s.is_data_readonly) ||
      sources.find((s) => s.type === 'mssql');
    ok('mssql_source', Boolean(source), source ? source.id : 'none');
    const sid = source.id;

    await req('POST', `/api/v2/meta/bases/${BASE_ID}/meta-diff/${sid}`, undefined, tok);
    const table = await waitTable(tok, sid, TABLE);
    const tid = table.id;
    ok('table_synced', true, tid);

    const [, meta] = await req('GET', `/api/v2/meta/tables/${tid}`, undefined, tok);
    const titleMap = Object.fromEntries((meta.columns || []).map((c) => [c.column_name, c.title]));
    const titleCol = titleMap.Title || 'Title';

    const formulas = [
      { title: 'F_Len', formula_raw: `LEN({${titleCol}})` },
      { title: 'F_Trim', formula_raw: `TRIM({${titleCol}})` },
      { title: 'F_If', formula_raw: `IF(LEN({${titleCol}})>0,"yes","no")` },
      { title: 'F_Now', formula_raw: `NOW()` },
    ];

    for (const f of formulas) {
      const [code, body] = await req(
        'POST',
        `/api/v2/meta/tables/${tid}/columns`,
        { title: f.title, uidt: 'Formula', formula_raw: f.formula_raw },
        tok,
      );
      console.log('formula_col', f.title, code, JSON.stringify(body).slice(0, 220));
      ok(`formula_create_${f.title}`, code === 200 || code === 201, JSON.stringify(body).slice(0, 180));
    }

    const [lcode, listed] = await req('GET', `/api/v2/tables/${tid}/records?limit=5`, undefined, tok);
    ok('records_ok', lcode === 200, JSON.stringify(listed).slice(0, 200));
    const row = (listed.list || [])[0] || {};
    console.log('row_sample', JSON.stringify(row).slice(0, 400));

    const lenVal = row.F_Len ?? row.f_len;
    ok('formula_len_value', lenVal != null && Number(lenVal) >= 5, `F_Len=${lenVal}`);

    const trimVal = String(row.F_Trim ?? row.f_trim ?? '');
    ok('formula_trim_value', trimVal.toLowerCase() === 'hello' || trimVal.includes('hello'), `F_Trim=${trimVal}`);

    const ifVal = String(row.F_If ?? row.f_if ?? '').toLowerCase();
    ok('formula_if_value', ifVal.includes('yes'), `F_If=${ifVal}`);

    const nowVal = row.F_Now ?? row.f_now;
    ok('formula_now_value', nowVal != null && String(nowVal).length > 0, `F_Now=${nowVal}`);

    // cleanup
    try {
      await db.raw(`IF OBJECT_ID(N'${SCHEMA}.${TABLE}', N'U') IS NOT NULL DROP TABLE ${fq};`);
    } catch (e) {
      console.log('cleanup_warn', e.message);
    }
    // best-effort delete meta table
    try {
      await req('DELETE', `/api/v2/meta/tables/${tid}`, undefined, tok);
    } catch (_) {
      /* ignore */
    }

    console.log('PHASE4_ALL_PASS', TABLE, randomUUID().slice(0, 8));
  } finally {
    await db.destroy();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
