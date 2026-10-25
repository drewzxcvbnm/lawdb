# Session handoff

Last updated: 25 October 2026.

## Start here

Read [PLAN.md](PLAN.md). It is the main record of the agreed product direction, repository audit, cost estimates, evaluation design, and implementation phases. This note records session state and practical details for resuming work.

The user ended this session after planning. No application implementation, embeddings, model evaluation, or paid AI processing has been performed. Do not interpret this handoff as permission to start paid processing or implement the entire plan without considering the user's next request.

## Decisions to preserve

- Search is the first product: relevant decisions, excerpts, filters, and original PDF page links.
- Offer both non-AI Keyword search and multilingual Smart search.
- Required query languages: Latvian, English, Russian. Other languages are welcome if they add little work; their quality is not yet validated.
- Run on localhost initially. Use hosted embedding APIs rather than local models.
- No confidential user facts in the initial scope.
- Budget is not fixed. Evaluate and forecast before full-corpus processing.
- OpenAI large is an evaluation baseline, not a proven winner or final commitment. Compare small and a multilingual alternative.
- Jev is an optional candidate for reranking/relevance assessment and later classification. It may be omitted if evaluation does not justify it. It does not replace embeddings.
- No legal expert has been identified. Use AI-assisted grading plus source-based targets and manual inspection, without claiming legal completeness.
- Preserve source versions and passage references so future collections, notes, comparisons, and cited answers can reuse them.

## Repository state at handoff

- Planning documents were added; application source and schema were not changed.
- No commit was created during this session. Check `git status` before work and preserve existing changes.
- Existing code: `download.py`, `load_postgres.py`, `db/schema.sql`, `docker-compose.yml`.
- Local data: `data/lawdb.sqlite`, `data/pdf/<prefix>/<uuid>.pdf`, `data/text/<prefix>/<uuid>.txt`.
- `.env` contains credentials. Its contents were not printed; continue keeping secrets out of logs and responses.
- The running database was reachable with `docker compose exec -T db psql -U lawdb lawdb`. Docker access required sandbox approval in this session; do not assume the next environment has identical permissions.

## Audit details worth retaining

The database contained exactly 429,910 metadata records and 429,909 document texts. The SQLite manifest had one failed download: a response labeled as PDF was not actually a PDF. Postgres occupied about 11 GB and local data about 56 GB.

The existing keyword search works. Its Latvian configuration is `simple` plus `unaccent`, without inflection stemming. One broad ranked query took 3.9 seconds; this is a single observation, not a measured latency distribution.

Page boundaries survive in extracted text as form-feed characters (`\f`). Preserve them before normalization. Three PDF page counts were checked against these boundaries. The extraction-quality sample contained 500 documents; it was not a full OCR audit.

The downloader skips previous successful downloads and the Postgres loader skips existing document texts. Replacement detection, withdrawals, content versions, and a source recheck policy still need design. Hashing alone cannot discover changes upstream.

Do not use ECLI as the only key: about 46% of records lack it. Do not label registration date as judgment date. Normalize inconsistent process labels without overwriting original source values.

## Cost estimate reproducibility

No documents were sent to an AI API during the audit. Token counts were calculated locally using `tiktoken` and `cl100k_base`.

The sample was selected by reading successful manifest rows ordered by document ID and applying Python `random.Random(42).sample(rows, 1000)`. It contained 14,975,359 characters and 7,093,421 tokens. The manifest's full character total was 6,726,599,550.

The rough chunking calculation assumed 800-token passages and 100-token overlap. Extrapolation gave about 3.19 billion source tokens and 3.61 billion billed tokens. These were arithmetic estimates, not the output of a completed paragraph-aware chunker.

The large-model forecast was approximately $470 standard or $235 Batch, using the rates recorded in PLAN.md. Reverify prices and measure actual pilot passage volume before spending. Jev, reranking, evaluation-model calls, and hosting are excluded.

Temporary tokenizer packages were installed under `/tmp/lawdb-audit-tokenizer`, with vocabulary cache under `/tmp/lawdb-audit-token-cache`. They may disappear and are not project dependencies. The audit used a Python 3.13 interpreter because the system Python was 3.14; do not depend on those temporary paths or add them to the application.

## Suggested next session

1. Read the user's new request and PLAN.md; inspect current working-tree and database state only as needed.
2. If proceeding with the pilot, create a reproducible representative selection of about 5,000 decisions and a question set covering all three required languages.
3. Establish page-aware passages and a keyword baseline before comparing paid embedding candidates.
4. Verify current model access and prices, estimate the pilot's actual costs, and establish the authorized processing scope before API calls.
5. Compare retrieval quality first, then the incremental value of reranking, including Jev if available.

Do not repeat the full repository investigation merely because this is a new session. Refresh findings when data, code, prices, or the task have changed.
