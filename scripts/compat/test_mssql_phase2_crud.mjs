/**
 * Phase 2 MSSQL CRUD acceptance (Node, knex+mssql, no pymssql).
 */
import { createRequire } from 'module';
import { randomUUID } from 'crypto';

const require = createRequire(import.meta.url);
const knex = require('knex');

const BACKEND = process.env.NC_BACKEND || 'http://127.0.0.1:6080';
const EMAIL = process.env.NC_TEST_EMAIL || 'mssql-ui-test@local.test';
const PASSWORD = process.env.NC_TEST_PASSWORD || '';
const BASE_ID = process.env.NC_BASE_ID || 'pw4yksn9i7x1fx4';
const EXISTING_SOURCE_ID = process.env.NC_MSSQL_SOURCE_ID || '';
const TRY_CREATE = process.env.NC_TRY_CREATE_SOURCE === '1';

const MSSQL = {
  host: process.env.NC_MSSQL_HOST || '192.168.1.11',
  port: Number(process.env.NC_MSSQL_PORT || 5678),
  user: process.env.NC_MSSQL_USER || 'sa',
  password: process.env.NC_MSSQL_PASSWORD || '',
  database: process.env.NC_MSSQL_DB || 'Metabase_ODS',
};
const SCHEMA = process.env.NC_MSSQL_SCHEMA || 'UFDATA';
const TABLE = process.env.NC_MSSQL_TABLE || `_nc_p2_${Math.floor(Date.now() / 1000)}`;

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
        try { payload = JSON.parse(raw); } catch { payload = { raw: raw.slice(0, 800) }; }
      }
      return [res.status, payload];
    } catch (e) {
      lastErr = e;
      console.log('req_retry', method, path, e.message);
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

async function createTable(db) {
  const fq = `[${SCHEMA}].[${TABLE}]`;
  await db.raw(`
    IF OBJECT_ID(N'${SCHEMA}.${TABLE}', N'U') IS NOT NULL DROP TABLE ${fq};
    CREATE TABLE ${fq} (
      Id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
      Title NVARCHAR(200) NOT NULL,
      Flag BIT NOT NULL CONSTRAINT DF_${TABLE}_flag DEFAULT(0),
      Amount DECIMAL(18,4) NULL,
      GuidCol UNIQUEIDENTIFIER NULL,
      TsCol DATETIME2(0) NULL,
      Note NVARCHAR(MAX) NULL
    );
  `);
  console.log(TABLE);
  return fq;
}

async function dropTable(db, fq) {
  await db.raw(`IF OBJECT_ID(N'${SCHEMA}.${TABLE}', N'U') IS NOT NULL DROP TABLE ${fq};`);
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
      const [c, body] = await req('POST', `/api/v2/meta/bases/${BASE_ID}/meta-diff/${sourceId}`, undefined, tok);
      console.log('meta_diff_nudge', i, c, JSON.stringify(body).slice(0, 120));
    }
    console.log(' wait table', i, tableName);
    await sleep(3000);
  }
  throw new Error('TABLE_SYNC_TIMEOUT');
}

async function ensureWritableSource(tok) {
  // Prefer existing UFDATA writable source (prod docker create path loses client / may OOM sync)
  let existing =
    (await listSources(tok)).find((s) => s.id === EXISTING_SOURCE_ID) ||
    (await listSources(tok)).find((s) => s.type === 'mssql' && !s.is_data_readonly);

  if (TRY_CREATE) {
    const alias = `mssql_p2_${Math.floor(Date.now() / 1000)}`;
    const body = {
      alias,
      type: 'mssql',
      fk_integration_id: existing?.fk_integration_id || 'intwmj52qoa3ash3w',
      config: { client: 'mssql', searchPath: [SCHEMA] },
      inflection_column: 'none',
      inflection_table: 'none',
      is_schema_readonly: true,
      is_data_readonly: false,
    };
    const [scode, job] = await req('POST', `/api/v2/meta/bases/${BASE_ID}/sources`, body, tok);
    console.log('create_source_job', scode, JSON.stringify(job).slice(0, 200));
    for (let i = 0; i < 15; i++) {
      await sleep(2000);
      const found = (await listSources(tok)).find((s) => s.alias === alias);
      if (found) {
        ok('create_writable_source', true, found.id);
        return { source: found, created: true };
      }
    }
    console.log('create_source_timeout_use_existing');
  }

  ok('create_writable_source', Boolean(existing), existing ? `existing:${existing.id}:${existing.alias}:searchPath=${SCHEMA}` : 'missing');
  if (existing?.is_data_readonly) {
    await req('PATCH', `/api/v2/meta/bases/${BASE_ID}/sources/${existing.id}`, { is_data_readonly: false }, tok);
  }
  // verify searchPath via get
  const [, detail] = await req('GET', `/api/v2/meta/bases/${BASE_ID}/sources/${existing.id}`, undefined, tok);
  console.log('source_config', JSON.stringify(detail.config || {}).slice(0, 200));
  return { source: existing, created: false };
}

async function main() {
  if (!PASSWORD) {
    console.error('Set NC_TEST_PASSWORD (and NC_MSSQL_PASSWORD for DDL)');
    process.exit(2);
  }
  if (!MSSQL.password) {
    console.error('Set NC_MSSQL_PASSWORD');
    process.exit(2);
  }

  const db = makeDb();
  let fq;
  let sid;
  let createdSource = false;
  try {
    const [hcode, health] = await req('GET', '/api/v1/health');
    console.log('health', hcode, health);
    ok('health', hcode === 200);

    const [, sign] = await req('POST', '/api/v1/auth/user/signin', { email: EMAIL, password: PASSWORD });
    const tok = sign.token;
    ok('signin', Boolean(tok));

    console.log('create isolation table');
    fq = await createTable(db);
    ok('ddl_create', true, fq);

    const ensured = await ensureWritableSource(tok);
    sid = ensured.source.id;
    createdSource = ensured.created;
    ok('source_ready', true, sid);

    const [mdCode, md] = await req('POST', `/api/v2/meta/bases/${BASE_ID}/meta-diff/${sid}`, undefined, tok);
    console.log('meta_diff', mdCode, JSON.stringify(md).slice(0, 200));

    const table = await waitTable(tok, sid, TABLE);
    const tid = table.id;
    ok('table_synced', true, tid);

    const [, meta] = await req('GET', `/api/v2/meta/tables/${tid}`, undefined, tok);
    const cols = Object.fromEntries((meta.columns || []).map((c) => [c.column_name, c]));
    console.log('columns', Object.keys(cols));
    ok('has_identity_id', 'Id' in cols);
    console.log('Id meta ai/pk', cols.Id?.ai, cols.Id?.pk, cols.Id?.id);

    const titleMap = Object.fromEntries((meta.columns || []).map((c) => [c.column_name, c.title]));
    const idTitle = titleMap.Id || 'Id';

    const insertBody = {
      [titleMap.Title || 'Title']: 'p2-row-1',
      [titleMap.Flag || 'Flag']: true,
      [titleMap.Amount || 'Amount']: 12.3456,
      [titleMap.GuidCol || 'GuidCol']: randomUUID(),
      [titleMap.TsCol || 'TsCol']: '2026-07-25 10:00:00',
      [titleMap.Note || 'Note']: 'phase2 crud',
    };
    const [icode, created] = await req('POST', `/api/v2/tables/${tid}/records`, insertBody, tok);
    console.log('insert resp', icode, JSON.stringify(created).slice(0, 400));
    ok('insert', icode === 200 || icode === 201, JSON.stringify(created).slice(0, 200));

    let createdRow = Array.isArray(created) ? created[0] || {} : created || {};
    let rowId = createdRow.Id ?? createdRow[idTitle];
    if (rowId == null) {
      const [lcode, listed] = await req('GET', `/api/v2/tables/${tid}/records?limit=5`, undefined, tok);
      const rows = listed.list || [];
      ok('list_after_insert', lcode === 200 && rows.length >= 1, JSON.stringify(listed).slice(0, 200));
      createdRow = rows[0];
      rowId = createdRow.Id ?? createdRow[idTitle];
    }
    ok('identity_backfill', rowId != null, `id=${rowId} row=${JSON.stringify(createdRow).slice(0, 200)}`);

    const upd = {
      [idTitle]: rowId,
      [titleMap.Title || 'Title']: 'p2-row-1-updated',
      [titleMap.Flag || 'Flag']: false,
      [titleMap.Amount || 'Amount']: 99.0001,
    };
    const [ucode, updated] = await req('PATCH', `/api/v2/tables/${tid}/records`, upd, tok);
    console.log('update resp', ucode, JSON.stringify(updated).slice(0, 300));
    ok('update', ucode === 200, JSON.stringify(updated).slice(0, 200));

    const [, listed2] = await req('GET', `/api/v2/tables/${tid}/records?limit=10`, undefined, tok);
    const match = (listed2.list || []).filter((r) => String(r.Id ?? r[idTitle]) === String(rowId));
    const titleVal = match[0]?.[titleMap.Title || 'Title'] ?? match[0]?.Title ?? '';
    ok('update_visible', match.length > 0 && String(titleVal).includes('updated'), JSON.stringify(match.slice(0, 1)).slice(0, 200));

    const [dcode, deleted] = await req('DELETE', `/api/v2/tables/${tid}/records`, { [idTitle]: rowId }, tok);
    console.log('delete resp', dcode, JSON.stringify(deleted).slice(0, 200));
    ok('delete', dcode === 200, JSON.stringify(deleted).slice(0, 200));

    const [, listed3] = await req('GET', `/api/v2/tables/${tid}/records?limit=10`, undefined, tok);
    const still = (listed3.list || []).filter((r) => String(r.Id ?? r[idTitle]) === String(rowId));
    ok('delete_gone', still.length === 0, `left=${still.length}`);

    const [pcode] = await req('PATCH', `/api/v2/meta/bases/${BASE_ID}/sources/${sid}`, { is_data_readonly: true }, tok);
    const [bcode, blocked] = await req('POST', `/api/v2/tables/${tid}/records`, { [titleMap.Title || 'Title']: 'should-fail' }, tok);
    const blockedStr = JSON.stringify(blocked).toLowerCase();
    console.log('readonly_block', pcode, bcode, JSON.stringify(blocked).slice(0, 200));
    ok('readonly_blocks_write', bcode >= 400 || blockedStr.includes('readonly') || blockedStr.includes('permission'), `code=${bcode}`);

    if (!createdSource) {
      await req('PATCH', `/api/v2/meta/bases/${BASE_ID}/sources/${sid}`, { is_data_readonly: false }, tok);
    }

    try { await dropTable(db, fq); console.log('dropped', fq); } catch (e) { console.log('cleanup_warn', e.message); }

    console.log('PHASE2_ALL_PASS', TABLE);
  } finally {
    await db.destroy();
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
