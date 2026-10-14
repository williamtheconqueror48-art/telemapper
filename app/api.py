"""TELEMAPPER HTTP API.

Same engine as the TUI, exposed as JSON endpoints.

Persistence: when DATABASE_URL is set, every search and its signals are
written to Postgres (Neon) with forensic fields (SHA256, IST timestamps),
and /api/export serves the evidence package as JSON or PDF. When DATABASE_URL
is unset, the API falls back to the in-memory SQLite ledger: scraping still
works, the forensic package rides inline in each response, and export
endpoints return 503.
"""

import os

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel

from app.crawler import PublicPreviewCrawler
from app.ledger import ForensicLedger

app = FastAPI(title="TELEMAPPER API", version="1.1.0")

_pg = None
_pg_failed = False


def _store():
    """Postgres store when DATABASE_URL is configured, else None."""
    global _pg, _pg_failed
    if _pg is not None:
        return _pg
    if _pg_failed or not os.environ.get("DATABASE_URL"):
        return None
    try:
        from app.pgstore import PgStore

        _pg = PgStore()
        return _pg
    except Exception:
        _pg_failed = True
        return None


def _fresh_crawler():
    # In-memory ledger: no disk on serverless, forensic package inline.
    ledger = ForensicLedger(db_path=":memory:")
    return PublicPreviewCrawler(ledger), ledger


def _forensic_package(ledger, channel):
    record = ledger.get_record(channel)
    if not record:
        return None
    return {
        "sha256": record["sha256"],
        "timestamp_ist": record["timestamp_ist"],
        "message_count": record["message_count"],
        "source": record["source"],
    }


def _channel_url(channel, message_id):
    if message_id:
        return f"https://t.me/{channel}/{message_id}"
    return f"https://t.me/s/{channel}"


@app.get("/api/health")
async def health():
    store = _store()
    return {
        "status": "ok",
        "service": "telemapper",
        "persistence": "postgres" if store else "memory",
    }


@app.get("/api/discover")
async def discover(keyword: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=25)):
    store = _store()
    search_id = store.create_search(f"discover:{keyword}") if store else None
    crawler, _ledger = _fresh_crawler()
    try:
        channels = await crawler.discover_by_keyword(keyword, limit=limit)
        if store:
            for ch in channels:
                store.log_discovery(
                    search_id, ch, "probe_pattern",
                    f"probe_match: {keyword}", 0, "discovered",
                )
            store.finish_search(search_id, len(channels))
        return {
            "keyword": keyword,
            "channels": channels,
            "count": len(channels),
            "search_id": search_id,
        }
    finally:
        await crawler.close()


@app.get("/api/channel/{channel}")
async def channel_signals(channel: str, pages: int = Query(2, ge=1, le=10)):
    # t.me/s serves ~20 messages per page; pages maps to a message budget.
    store = _store()
    search_id = store.create_search(f"channel:{channel}") if store else None
    crawler, ledger = _fresh_crawler()
    try:
        messages = await crawler.scrape_channel(channel, max_depth=pages * 20)
        if store:
            for m in messages:
                store.add_signal(
                    search_id, channel, m.get("id"), m.get("text"),
                    m.get("forward_source"),
                    _channel_url(channel, m.get("id")),
                )
            store.finish_search(search_id, len(messages))
        return {
            "channel": channel,
            "message_count": len(messages),
            "messages": messages,
            "forensic": _forensic_package(ledger, channel),
            "search_id": search_id,
        }
    finally:
        await crawler.close()


class ExpandRequest(BaseModel):
    seed: str
    keyword: str
    max_hops: int = 2


@app.post("/api/expand")
async def expand(req: ExpandRequest):
    if req.max_hops < 1 or req.max_hops > 3:
        raise HTTPException(status_code=400, detail="max_hops must be 1-3")
    store = _store()
    search_id = store.create_search(f"expand:{req.seed}:{req.keyword}") if store else None
    crawler, _ledger = _fresh_crawler()
    try:
        channels = await crawler.expand_forward_chain(req.seed, req.keyword, max_hops=req.max_hops)
        if store:
            for ch in channels:
                store.log_discovery(
                    search_id, ch, "forward_chain",
                    f"seed: {req.seed}", req.max_hops, "discovered",
                )
            store.finish_search(search_id, len(channels))
        return {
            "seed": req.seed,
            "keyword": req.keyword,
            "channels": channels,
            "count": len(channels),
            "search_id": search_id,
        }
    finally:
        await crawler.close()


@app.get("/api/export")
async def export_evidence(
    search_id: int = Query(..., ge=1),
    format: str = Query("json", pattern="^(json|pdf)$"),
):
    store = _store()
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Persistence not configured: set DATABASE_URL to enable exports.",
        )
    search = store.get_search(search_id)
    if search is None:
        raise HTTPException(status_code=404, detail=f"search_id {search_id} not found")
    signals = store.get_signals(search_id)
    discoveries = store.get_discoveries(search_id)

    if format == "json":
        return {"search": search, "signals": signals, "discoveries": discoveries}

    from app.evidence_pdf import build_evidence_pdf

    pdf_bytes = build_evidence_pdf(search, signals, discoveries)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="telemapper-evidence-{search_id}.pdf"'
        },
    )
