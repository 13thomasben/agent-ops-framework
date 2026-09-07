"""Tiny forward-only migration runner: applies db/NNN_*.sql in order, once each."""
import os
import sys
from pathlib import Path

import psycopg

HERE = Path(__file__).parent


def migrate(database_url: str | None = None) -> list[str]:
    url = database_url or os.environ["DATABASE_URL"]
    applied: list[str] = []
    with psycopg.connect(url) as conn:
        conn.execute(
            "create table if not exists schema_migrations ("
            " name text primary key, applied_at timestamptz not null default now())"
        )
        done = {r[0] for r in conn.execute("select name from schema_migrations")}
        for sql_file in sorted(HERE.glob("[0-9][0-9][0-9]_*.sql")):
            if sql_file.name in done:
                continue
            conn.execute(sql_file.read_text())
            conn.execute("insert into schema_migrations (name) values (%s)", (sql_file.name,))
            applied.append(sql_file.name)
        conn.commit()
    return applied


if __name__ == "__main__":
    names = migrate(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"applied: {names or 'nothing (up to date)'}")
