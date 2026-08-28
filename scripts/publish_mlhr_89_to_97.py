# -*- coding: utf-8 -*-
"""Publish mlhr talent tables: schema+data from 192.168.100.89 -> 192.168.100.97.

Does not touch 简历信息表 / 人才库需求表.
Requires MLHR_PG_PASSWORD (default Pass@w0rd for lab).
"""
from __future__ import annotations

import os
import sys

import psycopg2

SRC_HOST = os.environ.get("MLHR_SRC_HOST", "192.168.100.89")
DST_HOST = os.environ.get("MLHR_DST_HOST", "192.168.100.97")
PG_USER = os.environ.get("MLHR_PG_USER", "postgres")
PG_PASSWORD = os.environ.get("MLHR_PG_PASSWORD", "")
PG_DB = os.environ.get("MLHR_PG_DB", "mldata")

TABLES = ["raw_resume", "candidate", "interview_note", "job_req", "op_log"]


def connect(host: str):
    return psycopg2.connect(
        host=host, port=5432, user=PG_USER, password=PG_PASSWORD, dbname=PG_DB
    )


def coltype(row) -> str:
    _table, _col, data_type, udt, charlen, nprec, nscale, _nullable, _default = row
    if data_type == "character varying":
        return f"VARCHAR({charlen})" if charlen else "TEXT"
    if data_type == "text":
        return "TEXT"
    if data_type == "bigint":
        return "BIGINT"
    if data_type == "integer":
        return "INT"
    if data_type == "boolean":
        return "BOOLEAN"
    if data_type == "numeric":
        return f"NUMERIC({nprec},{nscale})" if nprec else "NUMERIC"
    if data_type == "date":
        return "DATE"
    if data_type.startswith("timestamp"):
        return "TIMESTAMPTZ" if "with time zone" in data_type else "TIMESTAMP"
    if udt == "jsonb":
        return "JSONB"
    return udt.upper()


def align_columns(src_cur, dst_cur) -> None:
    src_cur.execute(
        """
        SELECT table_name, column_name, data_type, udt_name,
               character_maximum_length, numeric_precision, numeric_scale,
               is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema='mlhr' AND table_name IN ('raw_resume','candidate')
        ORDER BY table_name, ordinal_position
        """
    )
    src_cols = src_cur.fetchall()
    dst_cur.execute(
        """
        SELECT table_name || '.' || column_name
        FROM information_schema.columns
        WHERE table_schema='mlhr' AND table_name IN ('raw_resume','candidate')
        """
    )
    have = {r[0] for r in dst_cur.fetchall()}
    for row in src_cols:
        key = f"{row[0]}.{row[1]}"
        if key in have:
            continue
        stmt = (
            f'ALTER TABLE mlhr."{row[0]}" '
            f'ADD COLUMN IF NOT EXISTS "{row[1]}" {coltype(row)}'
        )
        print("ADD", stmt)
        dst_cur.execute(stmt)


def copy_tables(src_cur, dst_cur) -> None:
    dst_cur.execute("SET session_replication_role = replica")
    # one shot: avoid CASCADE wiping earlier inserts via cross-FKs
    dst_cur.execute(
        'TRUNCATE TABLE mlhr.interview_note, mlhr.candidate, mlhr.raw_resume, '
        'mlhr.job_req, mlhr.op_log RESTART IDENTITY CASCADE'
    )
    for table in TABLES:
        src_cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='mlhr' AND table_name=%s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        cols = [r[0] for r in src_cur.fetchall()]
        dst_cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='mlhr' AND table_name=%s
            """,
            (table,),
        )
        dcols = {r[0] for r in dst_cur.fetchall()}
        cols = [c for c in cols if c in dcols]
        col_list = ",".join(f'"{c}"' for c in cols)
        print(f"copy {table} cols={len(cols)}")
        src_cur.execute(f'SELECT {col_list} FROM mlhr."{table}"')
        rows = src_cur.fetchall()
        if rows:
            placeholders = ",".join(["%s"] * len(cols))
            insert = f'INSERT INTO mlhr."{table}" ({col_list}) VALUES ({placeholders})'
            batch = 500
            for i in range(0, len(rows), batch):
                dst_cur.executemany(insert, rows[i : i + batch])
            print(f"  inserted {len(rows)}")
        else:
            print("  empty")
        dst_cur.execute(
            f"""
            SELECT setval(
              pg_get_serial_sequence('mlhr."{table}"', 'id'),
              COALESCE((SELECT MAX(id) FROM mlhr."{table}"), 1)
            )
            """
        )
        print("  seq", dst_cur.fetchone()[0])
    dst_cur.execute("SET session_replication_role = DEFAULT")


def verify(src_cur, dst_cur) -> None:
    for table in TABLES:
        src_cur.execute(f'SELECT count(*) FROM mlhr."{table}"')
        dst_cur.execute(f'SELECT count(*) FROM mlhr."{table}"')
        print(f"count {table}: src={src_cur.fetchone()[0]} dst={dst_cur.fetchone()[0]}")


def main() -> int:
    if not PG_PASSWORD:
        print("Set MLHR_PG_PASSWORD", file=sys.stderr)
        return 2
    src = connect(SRC_HOST)
    dst = connect(DST_HOST)
    try:
        sc, dc = src.cursor(), dst.cursor()
        align_columns(sc, dc)
        dst.commit()
        print("columns aligned")
        copy_tables(sc, dc)
        dst.commit()
        verify(sc, dc)
        print("DATA COPY OK")
        return 0
    except Exception:
        dst.rollback()
        raise
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    sys.exit(main())
