# Session handoff

Last updated: 26 October 2026.

## Current direction

Read [PLAN.md](PLAN.md). The user changed the immediate priority to a simple,
non-AI fullstack search application. This is now implemented. The multilingual
embedding pilot and Smart search are deferred; no paid AI processing has occurred.

## Application

- `app/main.py`: FastAPI API, read-only psycopg connection pool, parameterized SQL,
  bounded search, live collection counts, page-aware text reader, local PDF serving.
- `app/static/`: responsive English interface, Latvian source text, filters,
  highlighted excerpts, pagination, URL state, accessible dialog reader.
- `pyproject.toml`, `uv.lock`: locked Python dependencies; no frontend build.
- `tests/test_app.py`: offline and opt-in live database integration tests.
- `tests/browser_check.py`: Chromium smoke checks and screenshots in `/tmp`.

Run:

```bash
uv sync --locked
docker compose up -d
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open http://127.0.0.1:8000. See README.md for search syntax and validation commands.
The app reads `.env`; do not print credentials. Optional `DATABASE_URL` overrides
local Postgres settings. No schema/data migration or edits were needed.

## Validation

Five tests passed, including real-corpus queries, exact case lookup, filters,
pagination, text pages, PDF range serving, and input validation. Browser checks
passed on desktop and mobile, including keyword search, empty results, reader,
PDF page links, safe source-text rendering, and no JavaScript errors.

Sandbox execution required escalation for dependency downloads, localhost server,
Postgres connectivity, and Chromium. Sandboxed TestClient runs stalled; the same
tests passed with local network access. A dependency emits a TestClient/httpx
deprecation warning; tests still pass.

## Scope and limitations

- Keyword search is non-AI and does not translate English/Russian questions.
- Search uses `lv` (`simple` + `unaccent`), without inflection stemming or typo matching.
- Exact identifiers use a separate mode and are case-sensitive.
- Search covers records with extracted text; missing-text count is shown separately.
- Results are paginated in groups of 20, with a next-page indicator, not total count.
  Maximum 500 pages; narrow filters beyond that. Broad queries can take seconds.
- Registration date is not a verified judgment date. Source category variants remain
  separate. ECLI is frequently missing; UUID is the document identity.
- Page mapping uses preserved form feeds. The prior extraction audit was a sample,
  not a full correctness/OCR audit. Check original PDFs for layout and context.
- Query text is not logged by the documented launch command, but URLs remain in
  browser history. The app is localhost-only, without authentication.
- No commit was created. Inspect `git status` and preserve changes.

## Existing corpus and ingestion

At planning audit: 429,910 metadata records and 429,909 extracted documents,
about 56 GB local files and 11 GB Postgres. One failed PDF download. Existing
files: `download.py`, `load_postgres.py`, `db/schema.sql`, `docker-compose.yml`.
Data: `data/lawdb.sqlite`, `data/pdf/<prefix>/<uuid>.pdf`,
`data/text/<prefix>/<uuid>.txt`.

The downloader skips successful downloads; the loader skips loaded texts.
Replacement/withdrawal detection and source-version policy remain future work.
Do not repeat the whole audit without a reason.

## Future AI work (only when requested)

The plan retains the ~5,000-document pilot, ~50 questions in LV/EN/RU, keyword /
vector / hybrid comparisons, and optional reranking including Jev. No model is
chosen. Recheck model access and prices and establish processing scope before
paid work. Preserve original source versions and stable references.

Original cost audit: deterministic `random.Random(42).sample(rows, 1000)` over
successful manifest rows ordered by ID; 14,975,359 characters and 7,093,421
`cl100k_base` tokens. Full character total 6,726,599,550. Estimated 3.19B source
tokens / 3.61B with illustrative 800-token chunks and 100-token overlap. Large
model forecast ~$470 standard / $235 Batch at planning rates, not authorization.
Temporary audit tokenizer paths under `/tmp` are not application dependencies.
