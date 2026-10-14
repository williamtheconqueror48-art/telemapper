# TELEMAPPER

Map public Telegram channels. Follow the forwards. Keep the receipts.

TELEMAPPER discovers public Telegram channels by keyword, scrapes their public previews, expands through forward chains, and seals everything into a forensic ledger: full raw HTML, SHA256, IST timestamp, machine MAC. Built for tracking how narratives and leak material move through public Telegram, e.g. the NEET paper-leak channel economy.

## Boundary: public data only

Everything comes from `https://t.me/s/{channel}`, the public web preview Telegram serves without a login. No auth, no sessions, no Bot API tokens, no private groups. The crawler enforces this in code: `fetch_page()` rejects any target containing `+`, `joinchat`, or `api/auth` with a MISSION_ABORT. If Telegram stops serving a page publicly, the crawler records nothing and moves on. Anything that would need a login is out of scope by design, not by accident.

## How discovery works

Telegram exposes no keyword search without authentication, so there are two mechanisms:

1. **Probe patterns** (`discover_by_keyword`): the keyword plus five handle patterns (`{kw}_leak`, `{kw}_scam`, `{kw}_hub`, `official_{kw}`, `{kw}verified`). Only patterns that resolve to a real public page are kept.
2. **Forward-chain expansion** (`expand_forward_chain`): forwarded messages name their source channel, so BFS over forwards is how the network reveals itself. This is the primary discovery mechanism. Each hop runs a keyword relevance check; irrelevant forwards are logged as `discovered_not_scraped`.

## Tags are candidates, not verdicts

The TUI tags channels `[K]` when the channel *name* contains "leak" or "scam", `[W]` otherwise. This is a triage heuristic on the name alone. A channel called "leak" may be an awareness channel, not a leak shop. Verify before labeling. The ledger records what was found, never what it means.

## Quickstart

```bash
pip install -r requirements.txt

# Terminal UI
python -m app.telemapper        # or: python diag_run.py (crash-capture wrapper)

# HTTP API
uvicorn app.api:app --reload

# Live checks
python verify_crawler.py        # fixed reference: the known-public "durov" channel
python test_neet.py             # live NEET keyword probe
```

API endpoints: `GET /api/health`, `GET /api/discover?keyword=&limit=10`, `GET /api/channel/{channel}?pages=2`, `POST /api/expand` with `{"seed": ..., "keyword": ..., "max_hops": 2}`.

## Forensic ledger

SQLite, two tables. `forensic_ledger` stores the complete raw HTML of every scraped page alongside its SHA256; `discovered_channels` logs every find with method, reason, hop distance and status. `seal_batch()` raises MISSION_ABORT if asked to ledger anything not from the public surface.

Storage note: full raw HTML per page is deliberate (custody means keeping the exact bytes that were hashed). A deep scrape at `max_depth=200` can add tens of MB per channel. Lower `max_depth` when disk matters. Default DB path is `./data/telemapper_forensics.db`; override with `TELEMAPPER_DB_PATH`.

## Deploying on Vercel

`api/index.py` re-exports the FastAPI app; `vercel.json` routes all paths to it. Honest caveats:

- **No persistent disk.** The API uses the ledger in `:memory:` mode and returns the forensic package (SHA256, timestamp) inline in each response. Nothing persists between invocations.
- **Function duration vs scrape latency.** Each channel page costs one HTTP fetch plus a 2-3s politeness sleep. Deep scrapes will exceed serverless time limits. Keep `pages` low (default 2) and treat the API as a triage surface; run deep scrapes locally.
- **Cold starts** add latency to the first request.
- **Telegram rate-limits datacenter IPs.** Aggressive or repeated scraping from cloud egress IPs can get throttled or blocked. The 2-3s randomized sleep helps; it does not guarantee immunity.

## Layout

```
app/
  __init__.py
  crawler.py      # PublicPreviewCrawler: fetch, parse, scrape, discover, expand
  ledger.py       # ForensicLedger: SQLite evidence log
  telemapper.py   # Textual TUI
  api.py          # FastAPI layer
api/index.py      # Vercel entrypoint
vercel.json
diag_run.py       # TUI crash-capture wrapper
test_neet.py      # live NEET probe
verify_crawler.py # fixed-reference check against "durov"
requirements.txt
```
