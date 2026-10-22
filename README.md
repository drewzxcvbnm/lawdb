# lawdb

Local copy of Latvia's published anonymized court decisions
([data.gov.lv "Anonimizētie nolēmumi"](https://data.gov.lv/dati/dataset/anonimizetie-nolemumi), CC0 1.0),
loaded into Postgres.

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
