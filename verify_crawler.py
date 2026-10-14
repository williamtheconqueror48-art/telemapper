"""Crawler verification: scrape the known-public 'durov' channel.

Pavel Durov's public channel is the fixed reference target. If this
returns messages, the fetch -> parse -> ledger pipeline is live.
"""

import asyncio

from app.crawler import PublicPreviewCrawler
from app.ledger import ForensicLedger


async def main():
    # Use a known public channel for verification
    watchlist = ["durov"]

    ledger = ForensicLedger()
    crawler = PublicPreviewCrawler(ledger)

    try:
        for channel in watchlist:
            print(f"Starting scrape for {channel}...")
            messages = await crawler.scrape_channel(channel, max_depth=5)
            print(f"Scraped {len(messages)} messages from {channel}.")
            for msg in messages:
                if msg['forward_source']:
                    print(f"Found structure signal: Forwarded from {msg['forward_source']}")
                else:
                    print(f"Message ID {msg['id']}: {msg['text'][:50]}...")
    finally:
        await crawler.close()


if __name__ == "__main__":
    asyncio.run(main())
