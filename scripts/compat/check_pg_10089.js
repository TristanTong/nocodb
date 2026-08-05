const { Client } = require("pg");
const c = new Client({
  host: "192.168.100.89",
  port: 5432,
  user: "postgres",
  password: "Pass@w0rd",
  database: "mlnoco",
  connectionTimeoutMillis: 8000,
});
c.connect()
  .then(() =>
    c.query(
      "select current_database() as db, count(*)::int as tables from information_schema.tables where table_schema='public'"
    )
  )
  .then((r) => {
    console.log("PG_OK", JSON.stringify(r.rows[0]));
    return c.end();
  })
  .catch((e) => {
    console.error("PG_FAIL", e.message);
    process.exit(1);
  });
