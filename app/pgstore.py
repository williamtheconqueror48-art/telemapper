"""Postgres-backed forensic store for the TELEMAPPER API.

Used when DATABASE_URL is set (Vercel -> Neon). Mirrors the SQLite
ForensicLedger's forensic fields (SHA256 per record, IST timestamps) without
storing full raw HTML payloads: message text plus its hash is what persists.

When DATABASE_URL is unset, the API falls back to the in-memory SQLite
ledger and persistence-dependent endpoints (export) report 503.
"""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def _ist_now_iso() -> str:
    return datetime.now(IST).isoformat()


def _signal_hash(channel, message_id, text, forward_source, url) -> str:
    canonical = json.dumps(
        {
            "channel": channel,
            "message_id": message_id,
            "text": text or "",
            "forward_source": forward_source,
            "url": url,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PgStore:
    def __init__(self, dsn: str | None = None):
        import psycopg2
        import psycopg2.extras

        self._psycopg2 = psycopg2
        self._extras = psycopg2.extras
        self.dsn = dsn or os.environ.get("DATABASE_URL")
        if not self.dsn:
            raise RuntimeError("DATABASE_URL is not set")
        self._ensure_schema()

    def _conn(self):
        return self._psycopg2.connect(self.dsn)

    def _ensure_schema(self):
        schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn = self._conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(schema_sql)
        finally:
            conn.close()

    # -- writes -----------------------------------------------------------

    def create_search(self, query: str, status: str = "running") -> int:
        conn = self._conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO searches (query, status) VALUES (%s, %s) RETURNING id",
                        (query, status),
                    )
                    return cur.fetchone()[0]
        finally:
            conn.close()

    def finish_search(self, search_id: int, result_count: int, status: str = "complete"):
        conn = self._conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE searches SET result_count = %s, status = %s WHERE id = %s",
                        (result_count, status, search_id),
                    )
        finally:
            conn.close()

    def add_signal(self, search_id, channel, message_id, text, forward_source, url) -> int:
        sha = _signal_hash(channel, message_id, text, forward_source, url)
        sealed = _ist_now_iso()
        conn = self._conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO signals
                           (search_id, channel, message_id, text, forward_source, url, sha256, sealed_at_ist)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                        (search_id, channel, str(message_id) if message_id is not None else None,
                         text, forward_source, url, sha, sealed),
                    )
                    return cur.fetchone()[0]
        finally:
            conn.close()

    def log_discovery(self, search_id, channel, method, reason, hop, status):
        conn = self._conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO discovered_channels
                           (search_id, channel, discovery_method, reason, hop_distance, status)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (search_id, channel, method, reason, hop, status),
                    )
        finally:
            conn.close()

    # -- reads ------------------------------------------------------------

    def get_search(self, search_id: int) -> dict | None:
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM searches WHERE id = %s", (search_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    def get_signals(self, search_id: int) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM signals WHERE search_id = %s ORDER BY id", (search_id,)
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_discoveries(self, search_id: int) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM discovered_channels WHERE search_id = %s ORDER BY id",
                    (search_id,),
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
