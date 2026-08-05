const fs = require('fs');
const s = fs.readFileSync(
  'D:/Project/nocodb/mlnocodb/packages/nocodb/docker/main.js',
  'utf8',
);
const marker =
  'NcError.notImplemented(`Database ${(null==e||null==(t=e.meta)?void 0:t.dbtype)||""} is not supported`)';
const i = s.indexOf(marker);
console.log('marker', i);
console.log(s.slice(i - 600, i + marker.length + 80).replace(/\s+/g, ' '));
console.log('mssql=== count', (s.match(/"mssql"===e\.client/g) || []).length);
console.log('MssqlClient', (s.match(/MssqlClient/g) || []).length);
