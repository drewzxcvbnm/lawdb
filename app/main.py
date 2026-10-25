"""Read-only local search API. Run: uv run uvicorn app.main:app --host 127.0.0.1."""

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from time import monotonic
from typing import Literal
from uuid import UUID
import os
import threading

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg import OperationalError
from psycopg.conninfo import make_conninfo
from psycopg.errors import QueryCanceled
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout
from starlette.middleware.trustedhost import TrustedHostMiddleware

ROOT = Path(__file__).resolve().parents[1]
PAGE_SIZE = 20
FIELDS = "d.id, d.court, d.case_number, d.application_number, d.ecli, d.process_type, d.material_type, d.court_instance, d.registration_date"
HEADLINE = "StartSel=⟦, StopSel=⟧, MaxWords=65, MinWords=25, MaxFragments=1"


@asynccontextmanager
async def lifespan(app):
    load_dotenv(ROOT / ".env")
    dsn = os.getenv("DATABASE_URL") or make_conninfo(
        host="127.0.0.1", port=os.getenv("POSTGRES_PORT", "5432"),
        dbname="lawdb", user="lawdb", password=os.getenv("POSTGRES_PASSWORD", ""),
    )
    app.state.pool = ConnectionPool(dsn, min_size=0, max_size=4, timeout=5,
        kwargs={"row_factory": dict_row, "connect_timeout": 5,
                "options": "-c default_transaction_read_only=on -c statement_timeout=20000"},
        open=True)
    app.state.catalog = None
    app.state.catalog_lock = threading.Lock()
    yield
    app.state.pool.close()


app = FastAPI(title="LawDB", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response


@app.exception_handler(QueryCanceled)
async def query_timeout(request, exc):
    return JSONResponse(status_code=504, content={"detail": "This search took too long. Add a court, date range, or more specific words."})


async def database_unavailable(request, exc):
    return JSONResponse(status_code=503, content={"detail": "The database is unavailable. Check that Docker Compose is running, then retry."})


app.add_exception_handler(OperationalError, database_unavailable)
app.add_exception_handler(PoolTimeout, database_unavailable)


@app.get("/api/catalog")
def catalog(request: Request):
    with request.app.state.catalog_lock:
        cached = request.app.state.catalog
        if cached and monotonic() - cached[0] < 60:
            return cached[1]
        with request.app.state.pool.connection() as db:
            result = db.execute("""SELECT count(*) AS decisions,
                (SELECT count(*) FROM documents) AS searchable,
                max(registration_date) AS latest_registration,
                array_agg(DISTINCT court ORDER BY court) FILTER (WHERE court <> '') AS courts,
                array_agg(DISTINCT process_type ORDER BY process_type) FILTER (WHERE process_type <> '') AS process_types,
                array_agg(DISTINCT court_instance ORDER BY court_instance) FILTER (WHERE court_instance <> '') AS instances
                FROM decisions""").fetchone()
        request.app.state.catalog = (monotonic(), result)
        return result


def search_sql(q, mode, court, process_type, instance, date_from, date_to, sort, page):
    """All values are bound parameters; SQL fragments are selected only by code."""
    conditions, params = [], {"q": q, "limit": PAGE_SIZE + 1, "offset": (page - 1) * PAGE_SIZE, "headline": HEADLINE}
    text_search = bool(q and mode == "text")
    if text_search:
        conditions.append("doc.tsv @@ query.term")
    elif q:
        conditions.append("(d.case_number = %(q)s OR d.application_number = %(q)s OR d.ecli = %(q)s OR d.id::text = %(q)s)")
    for column, value in [("court", court), ("process_type", process_type), ("court_instance", instance)]:
        if value:
            conditions.append(f"d.{column} = %({column})s")
            params[column] = value
    for column, op, value in [("date_from", ">=", date_from), ("date_to", "<=", date_to)]:
        if value:
            conditions.append(f"d.registration_date {op} %({column})s")
            params[column] = value
    where = " AND ".join(conditions) or "TRUE"
    rank = "ts_rank_cd(doc.tsv, query.term)" if text_search else "0"
    order = "rank DESC, registration_date DESC NULLS LAST, id" if sort == "relevance" and text_search else "registration_date " + ("ASC" if sort == "oldest" else "DESC") + " NULLS LAST, id"
    # Rank/filter first, then fetch bodies and generate excerpts only for this page.
    excerpt = "ts_headline('lv', p.body, query.term, %(headline)s)" if text_search else "left(p.body, 420)"
    page_order = "ts_rank_cd(to_tsvector('lv', p.body), query.term) DESC, p.page" if text_search else "p.page"
    sql = f"""WITH query AS (SELECT websearch_to_tsquery('lv', %(q)s) AS term),
        candidates AS MATERIALIZED (
          SELECT {FIELDS}, {rank} AS rank
          FROM decisions d JOIN documents doc ON doc.decision_id = d.id CROSS JOIN query
          WHERE {where} ORDER BY {order} LIMIT %(limit)s OFFSET %(offset)s
        )
        SELECT c.*, excerpt.snippet, excerpt.page AS match_page
        FROM candidates c JOIN documents doc ON doc.decision_id = c.id CROSS JOIN query
        CROSS JOIN LATERAL (
          SELECT {excerpt} AS snippet, p.page
          FROM unnest(string_to_array(doc.body, chr(12))) WITH ORDINALITY AS p(body, page)
          ORDER BY {page_order} LIMIT 1
        ) excerpt ORDER BY {order}"""
    return sql, params


@app.get("/api/search")
def search(request: Request, q: str = Query("", max_length=300),
           mode: Literal["text", "identifier"] = "text", court: str = Query("", max_length=200),
           process_type: str = Query("", max_length=200), instance: str = Query("", max_length=200),
           date_from: date | None = None, date_to: date | None = None,
           sort: Literal["relevance", "newest", "oldest"] = "relevance",
           page: int = Query(1, ge=1, le=500)):
    q = q.strip()
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Start date must be on or before end date.")
    started = monotonic()
    with request.app.state.pool.connection() as db:
        if q and mode == "text":
            tree = db.execute("SELECT querytree(websearch_to_tsquery('lv', %s)) AS tree", (q,)).fetchone()["tree"]
            if not tree or tree == "T":
                raise HTTPException(422, "Include at least one word to search for, rather than only punctuation or excluded words.")
        sql, params = search_sql(q, mode, court, process_type, instance, date_from, date_to, sort, page)
        rows = db.execute(sql, params).fetchall()
    return {"items": rows[:PAGE_SIZE], "page": page, "page_size": PAGE_SIZE,
            "has_more": len(rows) > PAGE_SIZE and page < 500, "page_limit": 500,
            "elapsed_ms": round((monotonic() - started) * 1000)}


@app.get("/api/decisions/{decision_id}")
def decision(request: Request, decision_id: UUID, page: int = Query(1, ge=1)):
    with request.app.state.pool.connection() as db:
        row = db.execute("""SELECT d.*, doc.body FROM decisions d
            LEFT JOIN documents doc ON doc.decision_id = d.id WHERE d.id = %s""", (decision_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Decision not found.")
    body = row.pop("body")
    pages = body.split("\f") if body is not None else []
    # pdftotext ends its last real page with a form feed.
    if pages and not pages[-1].strip():
        pages.pop()
    if page > max(1, len(pages)):
        raise HTTPException(404, "Page not found.")
    row.update(text=pages[page - 1] if pages else "", page=page, page_count=len(pages),
               pdf_available=pdf_path(decision_id).is_file())
    return row


def pdf_path(decision_id: UUID):
    identifier = str(decision_id)
    return ROOT / "data" / "pdf" / identifier[:2] / f"{identifier}.pdf"


@app.get("/api/decisions/{decision_id}/pdf")
def pdf(decision_id: UUID):
    path = pdf_path(decision_id)
    if not path.is_file():
        raise HTTPException(404, "This PDF is not available locally.")
    return FileResponse(path, media_type="application/pdf", filename=f"{decision_id}.pdf", content_disposition_type="inline")


@app.get("/")
def index():
    return FileResponse(ROOT / "app" / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")
