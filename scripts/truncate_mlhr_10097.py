# -*- coding: utf-8 -*-
"""Truncate mlhr talent tables on 192.168.100.97 and reset id sequences."""
from __future__ import annotations

import os
import sys

import psycopg2

HOST = os.environ.get("MLHR_PG_HOST", "192.168.100.97")
TABLES = ["interview_note", "candidate", "raw_resume", "job_req", "op_log"]


def main() -> int:
    password = os.environ.get("MLHR_PG_PASSWORD", "")
    if not password:
        print("Set MLHR_PG_PASSWORD", file=sys.stderr)
        return 2

    conn = psycopg2.connect(
        host=HOST, port=5432, user="postgres", password=password, dbname="mldata"
    )
    cur = conn.cursor()
    cur.execute(
        "TRUNCATE TABLE mlhr.interview_note, mlhr.candidate, mlhr.raw_resume, "
        "mlhr.job_req, mlhr.op_log RESTART IDENTITY CASCADE"
    )
    conn.commit()
    print("TRUNCATE OK")

    for table in TABLES:
        cur.execute(f'SELECT count(*) FROM mlhr."{table}"')
        cnt = cur.fetchone()[0]
        cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (f"mlhr.{table}",))
        seq = cur.fetchone()[0]
        nxt = "n/a"
        if seq:
            cur.execute(f"SELECT last_value, is_called FROM {seq}")
            last_val, is_called = cur.fetchone()
            nxt = 1 if not is_called else last_val + 1
        print(f"{table}: rows={cnt}, seq={seq}, next_id={nxt}")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
