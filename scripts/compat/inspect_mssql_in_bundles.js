const fs = require('fs');

const files = [
  'D:/Project/nocodb/mlnocodb/packages/nocodb/docker/main.js',
  'D:/Project/nocodb/mlnocodb/packages/nocodb/dist/main.js',
];

for (const f of files) {
  if (!fs.existsSync(f)) {
    console.log(JSON.stringify({ file: f, missing: true }));
    continue;
  }
  const s = fs.readFileSync(f, 'utf8');
  const idx = s.indexOf('is not supported');
  const around =
    idx >= 0 ? s.slice(Math.max(0, idx - 400), idx + 200).replace(/\s+/g, ' ') : '';
  const checks = {
    file: f.replace(/.*packages/, 'packages'),
    size: s.length,
    mssqlCount: (s.match(/mssql/gi) || []).length,
    hasMssqlClient: /MssqlClient/.test(s),
    hasRequireMssql: /require\(["']mssql["']\)/.test(s),
    eqMssqlCount: (s.match(/===["']mssql["']|["']mssql["']===/g) || []).length,
    caseMssql: (s.match(/case\s*["']mssql["']/g) || []).length,
    factorySnippet: around.slice(0, 500),
  };
  console.log(JSON.stringify(checks, null, 2));
}
