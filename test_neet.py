"""Live probe: discover and scrape public Telegram channels for "NEET".

NEET paper leaks circulate through public Telegram channels; this script
exercises the full pipeline (discover -> scrape -> ledger) against live
t.me/s/ previews. Public data only, no login.
"""

import asyncio

from app.crawler import PublicPreviewCrawler
from app.ledger import ForensicLedger


async def test_neet_discovery():
    ledger = ForensicLedger()
    crawler = PublicPreviewCrawler(ledger)

    print("--- STARTING LIVE PROBE: 'NEET' ---")
    try:
        candidates = await crawler.discover_by_keyword("NEET", limit=10)
        print(f"Discovered Candidates: {candidates}")

        if not candidates:
            print("No candidates found via probe patterns.")
            return

        all_signals = []
        for channel in candidates:
            print(f"Scraping @{channel}...")
            msgs = await crawler.scrape_channel(channel, max_depth=5)
            for m in msgs:
                all_signals.append({
                    "channel": channel,
                    "text": m['text'][:50] if m['text'] else "Empty",
                    "forward": m['forward_source'] or "NONE"
                })

        print("\n--- LIVE SIGNALS RETRIEVED ---")
        for sig in all_signals:
            print(f"[@{sig['channel']}] {sig['forward']} | {sig['text']}...")

    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        await crawler.close()


if __name__ == '__main__':
    asyncio.run(test_neet_discovery())
