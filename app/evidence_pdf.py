"""Forensic evidence report PDF for TELEMAPPER exports.

Evidence-document layout: banner header, search metadata, then one package
block per signal (channel, message id, forward source, snippet, SHA256,
IST seal timestamp). Built with fpdf2 (pure Python, no system deps).
"""

from datetime import datetime, timedelta, timezone
from fpdf import FPDF, XPos, YPos

IST = timezone(timedelta(hours=5, minutes=30))


def _safe(text) -> str:
    # fpdf2 core fonts are latin-1; strip anything outside it.
    return (text or "").encode("latin-1", "replace").decode("latin-1")


class _Report(FPDF):
    def footer(self):
        self.set_y(-18)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Page {self.page_no()}/{{nb}}", align="C")


def build_evidence_pdf(search: dict, signals: list, discoveries: list) -> bytes:
    p = _Report(format="A4")
    p.alias_nb_pages("{nb}")
    p.set_auto_page_break(True, margin=20)
    p.set_margins(18, 15, 18)
    p.add_page()

    # -- banner header ------------------------------------------------------
    p.set_fill_color(3, 7, 8)
    p.rect(0, 0, 210, 34, "F")
    p.set_xy(18, 8)
    p.set_font("Helvetica", "B", 22)
    p.set_text_color(0, 255, 102)
    p.cell(0, 10, "TELEMAPPER", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    p.set_font("Helvetica", "", 10)
    p.set_text_color(192, 192, 192)
    p.cell(0, 6, "FORENSIC EVIDENCE REPORT", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    p.ln(12)

    def section(title):
        p.ln(4)
        p.set_font("Helvetica", "B", 13)
        p.set_text_color(3, 7, 8)
        p.cell(0, 8, _safe(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        p.set_draw_color(0, 255, 102)
        p.set_line_width(0.6)
        p.line(18, p.get_y(), 192, p.get_y())
        p.ln(3)

    def meta_row(label, value):
        p.set_font("Helvetica", "B", 10)
        p.set_text_color(40, 40, 40)
        p.cell(42, 6, _safe(label))
        p.set_font("Helvetica", "", 10)
        p.set_text_color(20, 20, 20)
        p.multi_cell(0, 6, _safe(str(value)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def kv(label, value, mono=False):
        p.set_font("Helvetica", "", 9)
        p.set_text_color(60, 60, 60)
        p.cell(32, 5, _safe(label))
        p.set_font("Courier" if mono else "Helvetica", "", 9)
        p.set_text_color(20, 20, 20)
        p.multi_cell(0, 5, _safe(str(value))[:160],
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def signal_block(idx, sig):
        if p.get_y() > 225:
            p.add_page()
        y0 = p.get_y()
        p.set_font("Helvetica", "B", 11)
        p.set_text_color(3, 7, 8)
        p.cell(0, 7, f"SIGNAL {idx:03d}  |  @{_safe(sig.get('channel'))}",
               new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        kv("Message ID", sig.get("message_id") or "-")
        kv("URL", sig.get("url") or "-")
        kv("Forwarded from", sig.get("forward_source") or "-")
        kv("Sealed (IST)", sig.get("sealed_at_ist") or "-")
        kv("SHA256", sig.get("sha256") or "-", mono=True)
        snippet = (sig.get("text") or "")[:600]
        kv("Snippet", snippet if snippet else "-")
        y1 = p.get_y()
        p.set_draw_color(200, 200, 200)
        p.rect(18, y0 - 1, 174, y1 - y0 + 3)
        p.ln(4)

    # -- search metadata ----------------------------------------------------
    s = search or {}
    section("SEARCH METADATA")
    meta_row("Search ID", s.get("id", "-"))
    meta_row("Query", s.get("query", "-"))
    meta_row("Created", s.get("created_at", "-"))
    meta_row("Status", s.get("status", "-"))
    meta_row("Result count", s.get("result_count", len(signals)))
    meta_row("Report generated (IST)", datetime.now(IST).isoformat(timespec="seconds"))
    meta_row("Source", "Public Telegram previews (t.me/s). No login, no private groups.")

    # -- signals ------------------------------------------------------------
    section(f"SIGNALS ({len(signals)})")
    for i, sig in enumerate(signals, 1):
        signal_block(i, sig)

    # -- discoveries ---------------------------------------------------------
    if discoveries:
        section(f"DISCOVERED CHANNELS ({len(discoveries)})")
        p.set_font("Helvetica", "", 9)
        p.set_text_color(20, 20, 20)
        for d in discoveries:
            p.cell(
                0, 6,
                _safe(f"@{d.get('channel')}  |  {d.get('discovery_method')}  "
                      f"|  hop {d.get('hop_distance')}  |  {d.get('status')}"),
                new_x=XPos.LMARGIN, new_y=YPos.NEXT,
            )

    return bytes(p.output())
