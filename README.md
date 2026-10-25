# lawdb

Local copy of Latvia's published anonymized court decisions
([data.gov.lv "Anonimizētie nolēmumi"](https://data.gov.lv/dati/dataset/anonimizetie-nolemumi), CC0 1.0),
loaded into Postgres.

## Local search application

The first app is entirely non-AI: a FastAPI backend, PostgreSQL full-text search,
and a responsive HTML/CSS/JavaScript frontend. It searches the existing collection;
no embedding service, API key, frontend build, or database migration is required.

With the database loaded using the setup below:

```bash
uv sync --locked
docker compose up -d
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open **http://127.0.0.1:8000**. The app reads `.env` using the same credentials as
the loader. `DATABASE_URL` can override the connection. It uses read-only database
transactions, a four-connection pool, and a 20-second SQL timeout.

- Search Latvian text, quoted phrases, `OR` alternatives, or exclude `-words`.
  Diacritics are ignored; inflected word endings are not merged and queries are
  not translated. At least one positive search term is required.
- Choose **Exact case number / ECLI / ID** to match a complete case number,
  application number, ECLI, or document UUID (case-sensitive).
- Filter by court, original case category, instance, and **registration date**.
  Sort by relevance or registration date; an empty query browses recent records.
- Read highlighted excerpts and open a page-by-page text reader or the local PDF
  at the excerpt's page. Page references use preserved `pdftotext` form feeds;
  inspect the PDF when layout or extraction quality matters.
- Search state and opened decisions are linkable through URL parameters.
  Search only includes records with extracted text; live collection counts show
  missing text separately. Counts are cached for 60 seconds.

Results use pages of 20 with a next-page indicator rather than an expensive total
match count. Browsing is capped at 500 pages; narrow the filters beyond that point.
Broad ranked searches can take several seconds. No source records or schema are
modified. Original category variants remain separate filter options.

The application makes no AI calls and stores no query logs. The command above
disables HTTP access logs; search URLs can still appear in browser history.
This is a localhost tool for public records, without user accounts or public
deployment configuration.

### Checks

```bash
uv run pytest -q                       # Offline validation and SQL construction
LAWDB_INTEGRATION=1 uv run pytest -q   # Also exercises your loaded DB (read-only)
# With the app running; set CHROMIUM_PATH if Chromium is elsewhere:
uv run python tests/browser_check.py
```

The browser check exercises desktop/mobile layouts, keyword search, empty results,
the decision reader, PDF page links, and safe rendering of source text. Screenshots
are saved in `/tmp/lawdb-desktop.png` and `/tmp/lawdb-mobile.png`.

Source: ~430k documents (2007–present). Metadata comes as one CSV from DAGR; each
document is a PDF from `gateway.elieta.lv`, no authentication required.

## Setup

Requires Docker, Python 3.11+, [uv](https://docs.astral.sh/uv/) and `pdftotext` (poppler).

```bash
cp .env.example .env                       # then set POSTGRES_PASSWORD (gitignored)
docker compose up -d                       # Postgres 17 + pgvector on 127.0.0.1:5432
python3 download.py metadata               # CSV -> data/lawdb.sqlite
python3 download.py documents --workers 3  # PDFs + text -> data/pdf, data/text (~56 GB, ~18 h)
uv run load_postgres.py                    # metadata + text -> Postgres (~10 GB, ~30 min)
docker compose exec db psql -U lawdb lawdb \
  -c "VACUUM ANALYZE decisions" -c "VACUUM ANALYZE documents"   # refresh planner stats after a bulk load
```

Every step is resumable; rerun to pick up where it stopped. Use
`download.py documents --sample N` for a deterministic subset, and `--retry-errors`
to retry failed downloads.

Refreshing (the source updates daily) fetches and loads only new or previously failed documents:

```bash
python3 download.py metadata --refresh && python3 download.py documents --retry-errors && uv run load_postgres.py
```

Monitoring a long download: `tail -f` its log for `done/total ok=… err=… rate eta` lines, or query the manifest:
`sqlite3 data/lawdb.sqlite "select status, count(*) from downloads group by status"`.

## Layout

| Path                             | Contents                                            |
| -------------------------------- | --------------------------------------------------- |
| `data/anonimizetie_nolemumi.csv` | Raw metadata CSV                                    |
| `data/lawdb.sqlite`              | Download manifest (`decisions`, `downloads`)        |
| `data/pdf/<xx>/<id>.pdf`         | Original PDFs, sharded by first two chars of the id |
| `data/text/<xx>/<id>.txt`        | `pdftotext` output                                  |
| `db/schema.sql`                  | Postgres schema (idempotent)                        |

## Postgres

Connect: `docker compose exec db psql -U lawdb lawdb` (no password needed inside the container).
From the host or other tools: `postgresql://lawdb:<POSTGRES_PASSWORD>@127.0.0.1:5432/lawdb`,
with the password from `.env`. The port is bound to localhost only.

Changing the password: `POSTGRES_PASSWORD` only applies when the volume is first created,
so update `.env` and also run `ALTER ROLE lawdb PASSWORD '...'` in psql.

- `decisions`: one row per document (court, case number, ECLI, type, date, status, instance, URL)
- `documents`: extracted text plus a generated `tsv` column with a GIN index

Postgres has no Latvian stemmer, so full-text search uses the `lv` config
(`simple` + `unaccent`): diacritics are ignored, inflected forms are not merged.
Use prefix queries (`ties:*`) to compensate.

```sql
SELECT d.case_number, d.court, d.registration_date
FROM documents doc JOIN decisions d ON d.id = doc.decision_id
WHERE doc.tsv @@ websearch_to_tsquery('lv', 'akcīzes cigaretes')
ORDER BY ts_rank(doc.tsv, websearch_to_tsquery('lv', 'akcīzes cigaretes')) DESC
LIMIT 10;
```

## Data quirks

- ~46% of decisions have no ECLI; use `case_number` / `application_number` for lookups.
- A few dozen rows have the placeholder `registration_date` 1970-01-01 (as published).
- The gateway occasionally serves a JSON error with `Content-Type: application/pdf`;
  the downloader records these as errors and `--retry-errors` picks them up later.

Reset the database: `docker compose down -v && docker compose up -d && uv run load_postgres.py`.
