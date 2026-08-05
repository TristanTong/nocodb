const fs = require('fs');
const s = fs.readFileSync(
  'D:/Project/nocodb/mlnocodb/packages/nocodb/docker/main.js',
  'utf8',
);

const needles = [
  'SqliteClient',
  'MySqlClient',
  'PgClient',
  'MssqlClient',
  'OracleClient',
  'YugabyteClient',
  'TidbClient',
  'VitessClient',
  'SqlClientFactory',
  "client===\"mysql\"",
  "client===\"sqlite3\"",
  "client===\"pg\"",
  "client===\"mssql\"",
  "client===\"oracledb\"",
  'is not supported',
  'Database ${',
  'Database not supported',
];

for (const n of needles) {
  const count = s.split(n).length - 1;
  console.log(count, n);
}

// find factory-like region by looking for sqlite3 client check nearby notSupported
let i = 0;
let hits = 0;
while ((i = s.indexOf('sqlite3', i)) !== -1 && hits < 5) {
  const snip = s.slice(Math.max(0, i - 120), i + 200).replace(/\s+/g, ' ');
  if (snip.includes('client') || snip.includes('Client')) {
    console.log('\n--- sqlite3 ctx ---');
    console.log(snip);
    hits++;
  }
  i += 7;
}

// look for notImplemented / not supported database message variants
for (const n of [
  'Database not supported',
  'is not supported',
  'notImplemented',
]) {
  let j = 0;
  let c = 0;
  while ((j = s.indexOf(n, j)) !== -1 && c < 3) {
    const snip = s.slice(Math.max(0, j - 250), j + 120).replace(/\s+/g, ' ');
    if (/Database|dbtype|client===|SqlClient|mysql|pg|sqlite/.test(snip)) {
      console.log(`\n--- ${n} ctx ---`);
      console.log(snip);
      c++;
    }
    j += n.length;
  }
}
