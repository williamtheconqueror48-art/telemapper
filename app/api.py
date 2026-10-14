"""TELEMAPPER HTTP API.

Same engine as the TUI, exposed as JSON endpoints. The ledger runs in
:memory: mode here because serverless functions have no persistent disk;
the forensic package (SHA256, IST timestamp) is returned inline in each
response instead of being read back from disk later.
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from app.crawler import PublicPreviewCrawler
from app.ledger import ForensicLedger

app = FastAPI(title="TELEMAPPER API", version="1.0.0")


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


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "telemapper"}


@app.get("/api/discover")
async def discover(keyword: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=25)):
    crawler, _ledger = _fresh_crawler()
    try:
        channels = await crawler.discover_by_keyword(keyword, limit=limit)
        return {"keyword": keyword, "channels": channels, "count": len(channels)}
    finally:
        await crawler.close()


@app.get("/api/channel/{channel}")
async def channel_signals(channel: str, pages: int = Query(2, ge=1, le=10)):
    # t.me/s serves ~20 messages per page; pages maps to a message budget.
    crawler, ledger = _fresh_crawler()
    try:
        messages = await crawler.scrape_channel(channel, max_depth=pages * 20)
        return {
            "channel": channel,
            "message_count": len(messages),
            "messages": messages,
            "forensic": _forensic_package(ledger, channel),
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
    crawler, _ledger = _fresh_crawler()
    try:
        channels = await crawler.expand_forward_chain(req.seed, req.keyword, max_hops=req.max_hops)
        return {"seed": req.seed, "keyword": req.keyword, "channels": channels, "count": len(channels)}
    finally:
        await crawler.close()
