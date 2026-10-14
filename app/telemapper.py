"""TELEMAPPER terminal UI.

Query bar -> discover public Telegram channels by keyword -> scrape their
public previews -> expand via forward chains -> results table with a
forensic signal package per row.

Tags: [K] = channel name contains "leak" or "scam", [W] = everything else.
These are CANDIDATE tags by channel-name keyword only, not verdicts.
A channel named "leak" may be an awareness channel, not a leak shop.
Verify before labeling.
"""

import jellyfish
import pyfiglet
from textual.app import App, ComposeResult
from textual.widgets import Input, DataTable, Static
from textual.containers import Container, Horizontal
from textual.binding import Binding

from app.crawler import PublicPreviewCrawler
from app.ledger import ForensicLedger

# Tactical colors
COLOR_BG = "#030708"
COLOR_PANEL = "#05080A"
COLOR_GREEN = "#00FF66"
COLOR_AMBER = "#FFB000"
COLOR_RED = "#FF3333"
COLOR_TEXT = "#C0C0C0"
COLOR_RULE = "#1B2631"


def candidate_tag(channel):
    """Candidate tag by channel-name keyword. Not a verdict."""
    name = (channel or "").lower()
    if "leak" in name or "scam" in name:
        return "[K]"
    return "[W]"


# jellyfish renamed jaro_winkler -> jaro_winkler_similarity in 1.x;
# support both spellings.
_jaro_winkler = getattr(jellyfish, "jaro_winkler_similarity",
                        getattr(jellyfish, "jaro_winkler", None))


class TelemapperApp(App):
    CSS = f"""
    Screen {{
        background: {COLOR_BG};
    }}
    #header-banner {{
        height: 7;
        content-align: center middle;
        color: {COLOR_GREEN};
        background: {COLOR_BG};
    }}
    #header-rule {{
        height: 1;
        background: {COLOR_RULE};
        width: 100%;
    }}
    #query-container {{
        height: 3;
        padding: 0 1;
    }}
    Input {{
        border: none;
        background: {COLOR_PANEL};
        color: {COLOR_GREEN};
    }}
    #main-body {{
        height: 1fr;
    }}
    DataTable {{
        background: {COLOR_BG};
        color: {COLOR_GREEN};
        border: none;
    }}
    #detail-panel {{
        width: 40;
        background: {COLOR_PANEL};
        border: solid {COLOR_RULE};
        padding: 1;
        color: {COLOR_TEXT};
    }}
    .status-bar {{
        height: 1;
        background: {COLOR_BG};
        color: #666666;
        padding: 0 1;
        text-align: left;
    }}
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        banner_text = pyfiglet.figlet_format("TELEMAPPER", font="block")
        yield Static(banner_text, id="header-banner")
        yield Static("", id="header-rule")

        with Container(id="query-container"):
            yield Input(placeholder="ENTER TARGET CHANNEL OR KEYWORD...", id="query-bar")

        with Horizontal(id="main-body"):
            yield DataTable(id="results-table")
            yield Static("SELECT A ROW FOR SIGNAL PACKAGE", id="detail-panel")

        yield Static("AWAITING QUERY", id="status-line", classes="status-bar")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("[INDEX]", "[CHANNEL / HANDLE]", "[LAST SIGNAL]")
        table.focus()
        self.ledger = ForensicLedger()
        self.signal_cache = {}

    def _cache_signal(self, channel, msg):
        """Cache one signal, return (row_key, channel_cell, signal_cell)."""
        signal_id = f"{channel}:{msg.get('id')}"
        text = msg.get("forward_source") or msg.get("text") or ""
        self.signal_cache[signal_id] = {
            "channel": channel,
            "text": text,
            "forward_of": msg.get("forward_source") or "NONE DETECTED",
            "id": msg.get("id"),
        }
        cell = text.replace("\n", " ").strip()[:50]
        return signal_id, f"{candidate_tag(channel)} @{channel}", cell

    async def _scrape_into(self, crawler, channel, rows):
        msgs = await crawler.scrape_channel(channel, max_depth=10)
        for msg in msgs:
            rows.append(self._cache_signal(channel, msg))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        target = event.value.strip()
        if not target:
            return

        status = self.query_one("#status-line")
        table = self.query_one(DataTable)

        status.update("DISCOVERING (probe patterns)...")
        status.styles.color = COLOR_AMBER

        crawler = PublicPreviewCrawler(self.ledger)

        try:
            candidates = await crawler.discover_by_keyword(target, limit=10)
            # Rank candidates by name similarity to the query.
            candidates.sort(
                key=lambda c: _jaro_winkler(target.lower(), c.lower()),
                reverse=True,
            )
            rows = []

            for channel in candidates:
                status.update(f"SCRAPING @{channel}...")
                await self._scrape_into(crawler, channel, rows)

            if candidates:
                seed = candidates[0]
                status.update("EXPANDING (forward-chain, hop 1/2)...")
                expanded = await crawler.expand_forward_chain(seed, target, max_hops=2)
                for channel in expanded:
                    status.update(f"SCRAPING @{channel}...")
                    await self._scrape_into(crawler, channel, rows)

            table.clear()
            if not rows:
                status.update("0 RESULTS - LIVE FETCH RETURNED EMPTY")
                status.styles.color = COLOR_RED
                return

            # Dedupe: t.me `?before=` pagination overlaps on the boundary
            # message, so the same message id can appear twice. The table
            # requires unique row keys; the ledger already sealed both pages.
            seen = set()
            unique_rows = []
            for signal_id, chan_cell, sig_cell in rows:
                if signal_id in seen:
                    continue
                seen.add(signal_id)
                unique_rows.append((signal_id, chan_cell, sig_cell))

            for idx, (signal_id, chan_cell, sig_cell) in enumerate(unique_rows, 1):
                # FIX: was key=s_//S_DATA["ID"] (NameError crash).
                # The detail panel looks rows up by this exact key.
                table.add_row(str(idx), chan_cell, sig_cell, key=signal_id)

            status.update(f"{len(unique_rows)} SIGNALS LIVE")
            status.styles.color = COLOR_GREEN

        except Exception as e:
            status.update(f"ERROR: {str(e)}")
            status.styles.color = COLOR_RED
        finally:
            await crawler.close()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # FIX: event.row_key is a RowKey object, not the raw string.
        # Comparing it directly against string keys always missed.
        raw_key = event.row_key
        key = raw_key.value if hasattr(raw_key, "value") else str(raw_key)
        panel = self.query_one("#detail-panel")

        if key in self.signal_cache:
            sig = self.signal_cache[key]
            record = self.ledger.get_record(sig["channel"])

            sha = record["sha256"][:12] if record else "Unknown"
            ts = record["timestamp_ist"] if record else "Unknown"

            snippet_clean = (sig["text"] or "")[:60].replace("\n", " ").strip()
            package = (
                "+- SIGNAL PACKAGE ----------------------------+\n"
                f"| CHANNEL   : @{sig['channel']:<30} |\n"
                f"| FORWARD_OF: {sig['forward_of']:<30} |\n"
                "| ------------------------------------------ |\n"
                "| SNIPPET   :                                  |\n"
                f'|  "{snippet_clean}..."                     |\n'
                "| ------------------------------------------ |\n"
                f"| LEDGER    : {sha}... | {ts}                |\n"
                "+--------------------------------------------+"
            )
            panel.update(package)
        else:
            panel.update(f"PANEL LOOKUP FAILED - KEY {key} NOT IN CACHE")


if __name__ == "__main__":
    app = TelemapperApp()
    app.run()
