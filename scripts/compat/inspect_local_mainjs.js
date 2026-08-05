const fs = require("fs");
const crypto = require("crypto");
const path = "D:/Project/nocodb/mlnocodb/packages/nocodb/docker/main.js";
const s = fs.readFileSync(path);
const hash = crypto.createHash("sha256").update(s).digest("hex");
const text = s.toString("utf8");
const mssqlCount = (text.match(/mssql/gi) || []).length;
const hasFactory = text.includes("Database ") && text.includes("is not supported");
const hasMssqlClient = /client===\"mssql\"|client==='mssql'|\"mssql\"===/.test(text);
console.log(
  JSON.stringify(
    {
      size: s.length,
      sha256: hash.slice(0, 16),
      mssqlCount,
      hasFactoryMsg: hasFactory,
      hasMssqlClientBranch: hasMssqlClient,
      snippet: (text.match(/Database \$\{[^}]+\} is not supported/) || [])[0],
    },
    null,
    2
  )
);
