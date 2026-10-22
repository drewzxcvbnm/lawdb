#!/usr/bin/env python3
"""Download Latvian anonymized court decisions (data.gov.lv "Anonimizētie nolēmumi").

Steps:
  metadata   fetch the DAGR CSV and load it into data/lawdb.sqlite
  documents  download PDFs and extract text with pdftotext (resumable)

Examples:
  python3 download.py metadata
  python3 download.py documents --sample 5000
  python3 download.py documents            # everything still missing
"""

import argparse
import csv
import random
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

CSV_URL = "https://dagr.gov.lv/public/kkp_prod_anon_nolemumi?filename=kkp_prod_anon_nolemumi.csv"
DATA = Path(__file__).resolve().parent / "data"
CSV_PATH = DATA / "anonimizetie_nolemumi.csv"
DB_PATH = DATA / "lawdb.sqlite"
USER_AGENT = "lawdb-research/0.1"

COLUMNS = [
    "MaterialFileId", "Court", "CourtDepartment", "EcliCode", "CaseNumber",
    "ApplicationNumber", "ProcessType", "ProcessSubType", "MaterialType",
    "RegistrationDate", "Status", "CourtInstance", "DownloadUrl",
]


def connect():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(f"""CREATE TABLE IF NOT EXISTS decisions (
        {', '.join(c + ' TEXT' for c in COLUMNS)},
        PRIMARY KEY (MaterialFileId))""")
    db.execute("""CREATE TABLE IF NOT EXISTS downloads (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,        -- ok | error
        pdf_bytes INTEGER,
        text_chars INTEGER,
        error TEXT,
        fetched_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return db


def cmd_metadata(args):
    DATA.mkdir(exist_ok=True)
    if args.refresh or not CSV_PATH.exists():
        print(f"downloading {CSV_URL}")
        tmp = CSV_PATH.with_suffix(".part")
        req = urllib.request.Request(CSV_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
        tmp.replace(CSV_PATH)
    db = connect()
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = set(COLUMNS) - set(reader.fieldnames)
        if missing:
            sys.exit(f"CSV schema changed, missing columns: {sorted(missing)}")
        rows = [tuple(r[c] for c in COLUMNS) for r in reader]
    with db:
        db.executemany(
            f"INSERT OR REPLACE INTO decisions VALUES ({','.join('?' * len(COLUMNS))})", rows)
    print(f"loaded {len(rows)} decisions into {DB_PATH}")


def paths_for(doc_id):
    shard = doc_id[:2]
    return DATA / "pdf" / shard / f"{doc_id}.pdf", DATA / "text" / shard / f"{doc_id}.txt"


def fetch(doc_id, url, retries, delay):
    """Download one PDF and extract its text. Runs in a worker thread."""
    pdf_path, txt_path = paths_for(doc_id)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.parent.mkdir(parents=True, exist_ok=True)

    if not pdf_path.exists():
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    body = resp.read()
                if not body.startswith(b"%PDF"):
                    raise ValueError(f"not a PDF ({resp.headers.get('Content-Type')})")
                tmp = pdf_path.with_suffix(".part")
                tmp.write_bytes(body)
                tmp.replace(pdf_path)
                break
            except urllib.error.HTTPError as e:
                # 4xx other than rate limiting won't fix itself
                if e.code not in (429, 500, 502, 503, 504) or attempt == retries:
                    return doc_id, "error", None, None, f"HTTP {e.code}"
            except Exception as e:
                if attempt == retries:
                    return doc_id, "error", None, None, f"{type(e).__name__}: {e}"
            time.sleep(min(60, 2 ** attempt * 2))
        time.sleep(delay)

    proc = subprocess.run(["pdftotext", "-q", "-enc", "UTF-8", str(pdf_path), str(txt_path)])
    if proc.returncode != 0:
        return doc_id, "error", pdf_path.stat().st_size, None, f"pdftotext exit {proc.returncode}"
    text_chars = len(txt_path.read_text(encoding="utf-8", errors="replace"))
    return doc_id, "ok", pdf_path.stat().st_size, text_chars, None


def cmd_documents(args):
    db = connect()
    if not db.execute("SELECT 1 FROM decisions LIMIT 1").fetchone():
        sys.exit("no metadata loaded; run: python3 download.py metadata")

    retry_clause = "OR d.status = 'error'" if args.retry_errors else ""
    todo = db.execute(f"""
        SELECT m.MaterialFileId, m.DownloadUrl FROM decisions m
        LEFT JOIN downloads d ON d.id = m.MaterialFileId
        WHERE d.id IS NULL {retry_clause}
        ORDER BY m.MaterialFileId""").fetchall()

    if args.sample:
        # Deterministic random sample over the whole corpus, so reruns pick the same docs
        all_ids = [r[0] for r in db.execute("SELECT MaterialFileId FROM decisions ORDER BY MaterialFileId")]
        chosen = set(random.Random(args.seed).sample(all_ids, min(args.sample, len(all_ids))))
        todo = [t for t in todo if t[0] in chosen]

    total = len(todo)
    print(f"{total} documents to fetch with {args.workers} workers")
    ok = err = 0
    started = time.time()
    with ThreadPoolExecutor(args.workers) as pool:
        futures = [pool.submit(fetch, i, u, args.retries, args.delay) for i, u in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            doc_id, status, pdf_bytes, text_chars, error = fut.result()
            db.execute("INSERT OR REPLACE INTO downloads (id, status, pdf_bytes, text_chars, error)"
                       " VALUES (?, ?, ?, ?, ?)", (doc_id, status, pdf_bytes, text_chars, error))
            ok += status == "ok"
            err += status == "error"
            if n % 100 == 0 or n == total:
                db.commit()
                rate = n / (time.time() - started)
                eta = (total - n) / rate if rate else 0
                print(f"{n}/{total} ok={ok} err={err} {rate:.1f}/s eta {eta / 60:.0f}m", flush=True)
    db.commit()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("metadata", help="download CSV and load into SQLite")
    m.add_argument("--refresh", action="store_true", help="re-download the CSV even if present")
    m.set_defaults(func=cmd_metadata)

    d = sub.add_parser("documents", help="download PDFs and extract text")
    d.add_argument("--sample", type=int, help="only a deterministic random sample of N documents")
    d.add_argument("--seed", type=int, default=42)
    d.add_argument("--workers", type=int, default=2)
    d.add_argument("--delay", type=float, default=0.3, help="seconds each worker waits between downloads")
    d.add_argument("--retries", type=int, default=4)
    d.add_argument("--retry-errors", action="store_true", help="also retry previously failed documents")
    d.set_defaults(func=cmd_documents)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
