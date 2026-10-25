# Court decision search: implementation and evaluation plan

Planning baseline: 25 October 2026. Updated 26 October 2026: the user chose to start with a standalone non-AI fullstack search application. That localhost application is now implemented; the embedding pilot and Smart search remain future work. Model prices and availability must be checked again before paid processing.

### Updated delivery order: keyword search first

The immediate milestone is a usable localhost application over the existing full-text index, before any AI evaluation. Implemented in `app/`: keyword and exact-identifier search, court/category/instance/registration-date filters, relevance/date sorting, pagination, highlighted source excerpts, page-aware reading, and original local PDF links. The frontend uses English labels and preserves Latvian source text and metadata.

The existing schema and downloaded corpus are reused without migration. See README.md for startup and tests. The multilingual pilot, model comparison, Smart search, and full vector indexing described below are deferred until requested. Keyword search does not translate queries or provide multilingual semantic retrieval.

## 1. Goal

Make Latvian public anonymized court decisions easy to find and inspect, including when users describe their problem in another language.

The first product is a search application. Users describe an issue or enter keywords, narrow results with filters, read relevant excerpts, and open the original decision at the relevant PDF page. Future research features should build on these same sources and references.

The first milestone is now non-AI search over the existing collection. A subsequent milestone is to demonstrate useful multilingual retrieval on a small collection before paying to index the full database.

## 2. Agreed constraints and scope

- Run the application and database on localhost initially.
- Generate embeddings through a hosted API. No local embedding model or GPU is required.
- Support Latvian, English, and Russian search queries from the first version.
- Allow other query languages where the chosen model supports them, without promising equal quality or building separate indexes for each language.
- Provide a genuinely non-AI keyword search mode alongside Smart search.
- Do not accept confidential facts in this initial version. Documents sent for embedding are from the public anonymized collection.
- Determine costs through evaluation before committing to full indexing. No fixed budget has been set.
- Use AI to assist relevance evaluation because no legal expert has been identified. Inspect examples ourselves and explicitly recognize the limits of AI judgments.
- Build search first, with foundations for future collections, notes, comparisons, and cited answers.

Query-language support and interface translation are separate matters. A fully localized interface has not yet been agreed.

## 3. Current repository and data

The repository already contains a resumable downloader, local PDFs, extracted text, a SQLite download manifest, a Postgres loader, and a Docker Compose database deployment.

| Item | Observed state |
| --- | --- |
| Metadata records | 429,910 |
| Downloaded and extracted documents | 429,909 |
| Failed downloads | One; gateway response was not a PDF |
| Local data directory | Approximately 56 GB |
| Postgres database | Approximately 11 GB |
| Extracted text | Approximately 6.73 billion characters |
| Database deployment | Postgres 17 image with pgvector 0.8.1 |
| Installed search extensions | `vector`, `pg_trgm`, `unaccent` |
| Existing keyword search | Generated full-text column and GIN index |
| Existing application | Local keyword search UI and read-only FastAPI API implemented 26 October 2026 |

Relevant files:

- [README.md](README.md): setup and data layout.
- [download.py](download.py): metadata/PDF ingestion and `pdftotext` extraction.
- [load_postgres.py](load_postgres.py): metadata and text loading.
- [db/schema.sql](db/schema.sql): metadata, document text, and search indexes.
- [docker-compose.yml](docker-compose.yml): local database deployment.

### Findings from the read-only audit

- A deterministic sample of 500 extracted texts contained no Unicode replacement characters. Spot checks showed readable Latvian text.
- The sample's median page-break count was two and its 95th percentile was nine. Page-break counts matched PDF page counts in three cross-checked documents.
- Only three manifest entries had fewer than 100 extracted characters. Some short documents are notices rather than failed extraction.
- These observations support reusing existing text. They do not prove that all pages were extracted correctly or that no OCR is needed.
- Approximately 46% of metadata records lack ECLI. Document UUIDs must remain the primary identifiers.
- Some process categories have singular/plural variants, and registration dates include placeholders. Preserve original values alongside normalized values.
- Registration date must not be presented as a verified judgment date.
- A broad ranked keyword query, `darba līgums`, matched roughly 34,500 documents and took about 3.9 seconds. This was one measurement, not a performance benchmark.

### Existing ingestion limitations

The downloader skips successful prior downloads, and the Postgres text loader skips already-loaded documents. Metadata refresh upserts records but does not reconcile all replacements or withdrawals.

Future ingestion needs a recheck policy, content hashes, document versions, and explicit handling of source removals or replacements. Hashes detect changes only after content is fetched; they do not themselves discover upstream changes.

## 4. How search will work

### Background processing

1. Discover new or changed decisions.
2. Download and retain the original PDF.
3. Extract text and preserve page boundaries.
4. Check text quality and flag suspect documents for investigation or OCR.
5. Split text into passages, respecting paragraphs and sections where practical.
6. Generate passage embeddings using a hosted API.
7. Store passage text, source references, processing versions, and embeddings in Postgres.
8. Build or update the relevant search indexes.

An embedding is a numerical representation used for similarity search. Generating embeddings does not train a model. The expensive collection processing happens ahead of searches, and unchanged documents do not need to be processed repeatedly.

### Keyword search

Use Postgres to search exact identifiers, words, phrases, and metadata without calling an AI provider. Support filters and relevant excerpts using the same result format as Smart search.

The existing Latvian configuration uses `simple` plus `unaccent`: it ignores diacritics but does not merge inflected word forms. Evaluate prefix matching and whether a Latvian dictionary is worth adding. Installed extensions alone do not imply that typo-tolerant search has been implemented.

Keyword mode does not automatically translate English or Russian questions into Latvian. Make that distinction understandable in the interface.

### Smart search

1. Accept the query and explicit filters.
2. Generate a query embedding with the same model and configuration used for documents, unless compatibility is explicitly guaranteed by the provider.
3. Retrieve candidate passages using pgvector and keyword search.
4. Optionally generate a Latvian query variant for the keyword branch, preserving case numbers and statutory references. Evaluate its benefit before making it a required step.
5. Combine candidate rankings, initially considering reciprocal rank fusion.
6. Optionally rerank a bounded shortlist using a hosted reranker.
7. Group passages by decision and return the strongest results with excerpts and PDF references.

The database performs vector search. An answering model such as Sol or Opus would later receive retrieved text, not raw embedding vectors. Changing the answering model does not require regenerating embeddings; changing the embedding model generally does.

Do not translate and embed the entire collection separately for each query language. One multilingual index is the intended approach.

### Starting experiments, not fixed settings

- Approximately 800 tokens per passage, with around 100 tokens of overlap.
- Paragraph/section-aware boundaries and neighboring context for important matches.
- Around 1,024 embedding dimensions where supported.
- A bounded shortlist, for example 100 passages, with results grouped into decisions.
- Approximate vector indexing, assessed against exact retrieval on a manageable subset.

Tune these choices using quality, latency, and storage measurements. In particular, test selective court/date filters with approximate retrieval so filtering does not silently leave too few relevant candidates.

## 5. Phase one: evaluation pilot

### Prepare a representative collection

Select about 5,000 decisions across courts, years, process types, document lengths, and document types. Include long judgments, short notices, abbreviated judgments, and difficult extraction examples. Keep a reproducible selection manifest.

Use existing local text initially. Establish reliable mappings from passages to source document versions and PDF pages. Avoid assuming an abbreviated judgment contains reasoning that was never published.

### Prepare research questions

Create approximately 50 research questions, each with Latvian, English, and Russian versions: roughly 150 query variants.

Include:

- Fact-pattern questions in ordinary language.
- Legal terminology and exact references.
- Narrow and broad questions.
- Similar facts involving different legal issues.
- Parties' allegations versus courts' conclusions.
- Questions with no known supporting material in the pilot collection.

For some questions, identify passages that demonstrably support an answer and record their source references. Also write natural questions independently of particular documents to avoid evaluating only artificially easy paraphrases. Equivalent translations should preserve the same issue rather than introduce foreign legal assumptions.

### Compare candidate models

| Candidate | Purpose |
| --- | --- |
| OpenAI `text-embedding-3-large` | Initial quality baseline and source of the current cost estimate |
| OpenAI `text-embedding-3-small` | Test whether a lower-cost model is sufficient |
| One current multilingual Cohere or Voyage model | Test whether another provider offers better Latvian or cross-language retrieval |

Choose the exact alternative after verifying current documentation, access, and prices. No model has yet been established as the best fit for this corpus.

Use the same source collection, passage construction, queries, and filters for fair comparisons. Keep incompatible embeddings separate. Compare keyword-only, vector-only, and hybrid results first; then test reranking on the strongest configurations.

### Evaluate Jev as an optional component

Jev, from TypeSafe AI, is a structured decision model: it evaluates supplied information against predefined questions or options and returns decisions with confidence estimates. It is a candidate for evaluation, not a committed dependency or a replacement for the embedding index. See [TypeSafe's introduction](https://typesafe.ai/blog/introducing-system-one-models-and-jev) and [provider overview](https://typesafe.ai/).

Potential uses in this project:

- **Relevance assessment:** score or filter the passages retrieved by hybrid search.
- **Passage classification:** distinguish parties' arguments, court reasoning, outcomes, and other content, including ambiguous or mixed passages.
- **Document categorization:** assign predefined topic labels as optional metadata enrichment.

Start with relevance assessment on a bounded shortlist. Compare the same retrieved candidates under three conditions: no reranking, a dedicated reranker, and Jev. Measure retrieval quality in Latvian, English, and Russian, latency, and actual API cost. In particular, check whether filtering discards known relevant passages; initially use scores for ordering rather than irreversible exclusion.

If useful, run a separate small classification experiment with inspected examples and an explicit uncertain/other option. Preserve the original text and keep predicted labels separate from source metadata. A model's guarantee of valid structured output does not establish that its decisions are correct, or that confidence is calibrated for Latvian legal material. Test any confidence thresholds on held-out examples.

Verify current API access, model versions, input limits, language performance, and pricing before testing. Existing embedding cost estimates do not include Jev. Adopt it only if measured gains justify the cost, latency, and added dependency; otherwise leave it out. Search must work without it.

### Judge quality without a legal expert

Use a separate answering model to assist relevance grading. Require supporting quotations and distinguish factual relevance from legal authority. Hide the retrieval model's identity from the judge where possible, and inspect disagreements and a sample of accepted results ourselves.

AI-generated questions and AI grading can share blind spots. Known supporting passages provide measurable retrieval targets, but they are not an exhaustive list of relevant authorities. An AI-only evaluation cannot establish legal completeness or professional reliability.

If Jev is used to rank or classify results, do not use its own judgments as the sole evaluation of those results. Retain known supporting passages, separate AI-assisted grading, and manual inspection as independent checks.

Keep some questions held out from tuning and report language-specific results. Do not choose a model based solely on an overall average that hides poor Russian or Latvian performance.

### Measurements and decision gate

- Whether known supporting decisions appear in the top 10 and top 20.
- Rank of the first relevant decision and graded relevance of the top results.
- Agreement across equivalent Latvian, English, and Russian queries.
- Irrelevant matches, duplicate results, and missing known sources.
- Typical and slow-query latency, with cache conditions and hardware recorded.
- Actual API usage, passage count, embedding storage, and index size.
- Incremental benefit and cost of translation and reranking.
- Jev's benefit relative to a dedicated reranker, relevant passages lost through filtering, and the reliability of any classification or confidence thresholds tested.

Before full indexing, document the chosen configuration, observed weaknesses, projected costs, and agreed acceptance targets. The gate is demonstrated usefulness and acceptable cost, not simply completion of the pilot.

## 6. Cost forecast

### Basis

The audit tokenized 1,000 deterministic sampled decisions with OpenAI's `cl100k_base` tokenizer and extrapolated against the manifest's total character count.

The sample contained approximately 14.98 million characters and 7.09 million tokens. Estimated full-corpus volume is 3.19 billion tokens before overlap and 3.61 billion tokens with the illustrative passage settings. Passage count is approximately 4.5–4.7 million, depending on extrapolation and final boundary rules.

### Initial embedding costs

| Scenario | Estimated API cost, USD |
| --- | ---: |
| Full collection, OpenAI large, standard | $470 |
| Full collection, OpenAI large, Batch | $235 |
| Full collection, OpenAI small, standard | $72 |
| Pilot of 5,000 average-length decisions, OpenAI large, standard | $5.50 |
| Same pilot through Batch | $3 |

These use the rates checked during planning: $0.13 per million tokens for large and $0.02 for small, with a 50% Batch discount. Sources: [OpenAI model pricing](https://developers.openai.com/api/docs/models/text-embedding-3-large) and [Batch API documentation](https://developers.openai.com/api/docs/guides/batch).

Allow roughly $250–350 for the initial large-model Batch run as a provisional planning envelope, not a spending authorization. The pilot's stratified selection may differ from the collection's average length. Alternative models and AI-assisted grading incur separate costs.

These figures exclude OCR, optional generated metadata, query translation, reranking, summaries, hosting, backups, taxes, and major reindexing experiments. Recalculate before committing to paid work.

### Ongoing costs and storage

- At 100 tokens per query, 100,000 query embeddings would cost approximately $1.30 with the large model at the planning rate.
- Embedding 1,000 new average-length decisions through Batch would cost roughly $1.10 under the same assumptions.
- Approximately 19 GB would be needed for raw 1,024-dimensional float vectors alone. Search indexes, passage text, row overhead, existing data, temporary build space, and backups are additional.
- The audited machine had approximately 31 GiB RAM and 500 GB free disk. This supports local experimentation but does not establish full-scale latency or capacity.
- Hosted API embeddings do not require a GPU. Postgres search still consumes local CPU, memory, and storage.

Measure actual usage in the pilot. Forecast monthly costs from new-document volume, query volume, candidate counts, and optional model calls. Do not infer ingestion growth solely from registration dates. Initial processing duration also depends on account quotas and batching limits.

## 7. Phase two: search MVP on localhost

Build one focused workflow:

1. Enter a question, keywords, or case identifier.
2. Select Smart or Keyword search.
3. Apply court, date, instance, and case-category filters where supported.
4. Inspect matching decisions and source excerpts.
5. Open the PDF at the relevant page and inspect surrounding context.

Results should include stable decision identifiers, available metadata, relevant passages, and source links. Distinguish original court text from any AI-generated explanation. Show index coverage and freshness accurately; a pilot index must not appear to search the full corpus.

The MVP need not generate an answer or summary for every query. Retrieval and evidence inspection come first. If an AI dependency fails, keep Keyword search usable and make any fallback explicit.

Keep runtime credentials on the server, outside tracked files. Avoid storing raw search queries by default; operational metrics can track latency, failures, and cost without retaining query text.

## 8. Foundations for future features

Keep the application simple: one backend, Postgres, and a resumable background processing path are sufficient starting points. A separate vector service or distributed architecture is not currently justified.

Design these boundaries from the beginning:

| Foundation | Why it matters |
| --- | --- |
| Stable decision and version identifiers | Notes and citations remain attached to the correct source |
| Passages with page numbers and text offsets | Search, highlighting, comparisons, and cited answers can reuse evidence |
| Preserved original and normalized text | Cleanup does not destroy traceability to the PDF |
| Versioned extraction, chunking, and embedding settings | Reprocessing can be controlled and compared |
| Processing status and usage records | Jobs can resume without repeating successful paid work |
| Separate metadata enrichment | Future summaries and classifications do not replace source facts |
| Shared search result contract | UI and future agent tools can use the same search service |
| Explicit provider boundary | Embedding and reranking providers can be evaluated or replaced |

Do not use passage ordinals alone as permanent citation identifiers: rechunking may change them. Preserve source version and location, and retain or migrate references when rebuilding.

Future additions include saved collections, notes, decision comparison, supporting and contrary reasoning, topic alerts, citation links, and cited research memos. These are architectural considerations, not requirements to implement in the search MVP.

## 9. Phase three: full indexing and verification

After the evaluation and cost decision:

1. Finalize the extraction, passage, embedding, and index configuration.
2. Perform a full quality inventory and isolate suspect documents rather than silently indexing empty or unusable text.
3. Process the collection in resumable jobs with bounded concurrency, retries, usage accounting, and duplicate-work protection.
4. Build and measure search indexes with adequate temporary disk headroom.
5. Re-run held-out search evaluations against the full corpus; a small pilot has fewer distracting candidates and can overstate quality.
6. Benchmark broad queries, selective filters, and all three required languages.
7. Verify citations, coverage reporting, keyword-only operation, and failure behavior.
8. Establish incremental ingestion and the source revision/withdrawal policy.

## 10. Remaining choices

The following should be settled through the pilot or implementation design:

- Exact alternative embedding model and any reranker.
- Whether Jev provides enough measured benefit to include for relevance assessment or later classification; omission is an acceptable outcome.
- Passage boundaries, overlap, dimensions, and index parameters.
- Measurable quality and latency acceptance targets.
- Whether query translation improves retrieval enough to justify its cost and latency.
- Initial interface language and backend/frontend framework choices.
- Source recheck frequency and handling of withdrawn or replaced documents.
- Whether user accounts are necessary when saved research features are introduced.

Public deployment, confidential inputs, outcome prediction, and broad automated legal advice are outside the initial scope. Revisit deployment and data-handling requirements if that scope changes.

## 11. Deliverables in order

The following original AI delivery sequence now follows the standalone non-AI application implemented first. It is retained as the future Smart-search roadmap.

1. Reproducible pilot collection and multilingual question set.
2. Evaluation report comparing relevance, latency, and cost.
3. Chosen search configuration and updated full-corpus forecast.
4. Localhost search MVP with Keyword and Smart modes, filters, excerpts, and PDF links.
5. Full index, held-out evaluation results, and incremental processing procedure.
6. A prioritized roadmap for research features built on the shared source references.

Success for the first release means users can find and verify useful decisions in Latvian, English, and Russian, while ordinary keyword search remains available independently of AI services.
