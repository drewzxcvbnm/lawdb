#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""Load metadata and extracted text from data/ into Postgres.

Reads data/lawdb.sqlite (filled by download.py) and data/text/. Safe to rerun:
existing rows are updated, documents already loaded are skipped.

  docker compose up -d
  uv run load_postgres.py
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SQLITE_PATH = DATA / "lawdb.sqlite"
SCHEMA = ROOT / "db" / "schema.sql"


def read_env_file(path=ROOT / ".env"):
    """Read KEY=VALUE lines from the same .env docker compose uses; real env vars win."""
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip())


def default_dsn():
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        sys.exit("POSTGRES_PASSWORD not set; put it in .env (see .env.example) or pass --dsn")
    return "postgresql://lawdb:{pw}@127.0.0.1:{port}/lawdb".format(
        pw=quote(password, safe=""), port=os.environ.get("POSTGRES_PORT", "5432"))

DECISION_COLUMNS = [
    "id", "court", "court_department", "ecli", "case_number", "application_number",
    "process_type", "process_subtype", "material_type", "registration_date", "status",
    "court_instance", "download_url",
]


def load_decisions(pg, lite):
    rows = lite.execute("""SELECT MaterialFileId, Court, CourtDepartment, EcliCode, CaseNumber,
        ApplicationNumber, ProcessType, ProcessSubType, MaterialType, RegistrationDate, Status,
        CourtInstance, DownloadUrl FROM decisions""")
    cols = ", ".join(DECISION_COLUMNS)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in DECISION_COLUMNS[1:])
    with pg.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE decisions_in (LIKE decisions) ON COMMIT DROP")
        with cur.copy(f"COPY decisions_in ({cols}) FROM STDIN") as copy:
            n = 0
            for row in rows:
                # The CSV uses empty strings for missing values
                copy.write_row([v or None for v in row])
                n += 1
        cur.execute(f"""INSERT INTO decisions ({cols}) SELECT {cols} FROM decisions_in
                        ON CONFLICT (id) DO UPDATE SET {updates}""")
    pg.commit()
    print(f"decisions: {n} upserted")


def load_documents(pg, lite, batch_size):
    downloaded = [r[0] for r in lite.execute("SELECT id FROM downloads WHERE status = 'ok'")]
    with pg.cursor() as cur:
        cur.execute("SELECT decision_id::text FROM documents")
        loaded = {r[0] for r in cur}
    todo = [i for i in downloaded if i not in loaded]
    print(f"documents: {len(downloaded)} downloaded, {len(loaded)} already loaded, {len(todo)} to load")

    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        with pg.cursor() as cur, cur.copy("COPY documents (decision_id, body) FROM STDIN") as copy:
            for doc_id in batch:
                text = (DATA / "text" / doc_id[:2] / f"{doc_id}.txt").read_text(
                    encoding="utf-8", errors="replace")
                # Postgres text cannot hold NUL bytes
                copy.write_row([doc_id, text.replace("\x00", "")])
        pg.commit()
        print(f"  {min(start + batch_size, len(todo))}/{len(todo)}", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"),
                   help="defaults to DATABASE_URL, else built from POSTGRES_PASSWORD in .env")
    p.add_argument("--batch-size", type=int, default=1000)
    args = p.parse_args()
    if not args.dsn:
        read_env_file()
        args.dsn = default_dsn()

    lite = sqlite3.connect(SQLITE_PATH)
    with psycopg.connect(args.dsn) as pg:
        pg.execute(SCHEMA.read_text())
        pg.commit()
        load_decisions(pg, lite)
        load_documents(pg, lite, args.batch_size)


if __name__ == "__main__":
    main()
