"""Forensic ledger: append-only evidence log backed by SQLite.

Two tables:
  forensic_ledger    - one row per sealed batch: target, source, the FULL
                       raw HTML payload, its SHA256, machine MAC, IST
                       timestamp, message count, public_surface_only flag.
  discovered_channels - every channel the crawler finds, with method,
                       reason, hop distance and status.

SIZE NOTE: seal_batch stores the complete raw HTML of every scraped page.
A deep scrape (max_depth=200 pages) can grow the database by tens of
megabytes per channel. This is deliberate: forensic custody means keeping
the exact bytes that were hashed. Budget disk accordingly, or lower
max_depth when storage matters.

Database location: env var TELEMAPPER_DB_PATH, default
./data/telemapper_forensics.db (directory is created if missing).
Pass db_path=":memory:" for serverless / ephemeral use (no disk writes).
"""

import datetime
import hashlib
import os
import sqlite3
import uuid
from typing import Optional, Dict, Any


def _resolve_db_path(db_path: Optional[str] = None) -> str:
    if db_path is not None:
        return db_path
    return os.environ.get("TELEMAPPER_DB_PATH", "./data/telemapper_forensics.db")


class ForensicLedger:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = _resolve_db_path(db_path)
        # :memory: databases die with their connection, so hold one open.
        self._mem_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:")
        else:
            parent = os.path.dirname(os.path.abspath(self.db_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        # NOTE: `with conn:` commits/rollbacks on exit; it does NOT close
        # the connection, so this is safe for the persistent :memory: conn.
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS forensic_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT NOT NULL,
                    source TEXT NOT NULL,
                    raw_payload TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    mac_address TEXT NOT NULL,
                    timestamp_ist TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    public_surface_only BOOLEAN NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS discovered_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel TEXT UNIQUE,
                    discovery_method TEXT,
                    reason TEXT,
                    hop_distance INTEGER,
                    status TEXT, -- 'scraped', 'discovered_not_scraped'
                    timestamp_ist TEXT
                )
            """)
            conn.commit()

    def _get_mac(self) -> str:
        try:
            return ':'.join(map(hex, uuid.getnode()))
        except Exception:
            return "UNKNOWN_MAC"

    def seal_batch(self, target: str, raw_html: str, message_count: int,
                   public_surface_only: bool) -> Optional[int]:
        if not public_surface_only:
            raise ValueError("MISSION_ABORT: Attempted to ledger non-public surface data.")

        payload_bytes = raw_html.encode('utf-8')
        sha256_hash = hashlib.sha256(payload_bytes).hexdigest()
        timestamp = datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=5, minutes=30))).isoformat()
        mac = self._get_mac()

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO forensic_ledger
                (target, source, raw_payload, sha256, mac_address, timestamp_ist, message_count, public_surface_only)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (target, "telegram_public_preview", raw_html, sha256_hash, mac, timestamp, message_count, 1))
            conn.commit()
            return cursor.lastrowid

    def log_discovery(self, channel: str, method: str, reason: str, hop: int, status: str):
        timestamp = datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=5, minutes=30))).isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO discovered_channels
                (channel, discovery_method, reason, hop_distance, status, timestamp_ist)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (channel, method, reason, hop, status, timestamp))
            conn.commit()

    def get_record(self, target: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM forensic_ledger WHERE target = ? ORDER BY id DESC LIMIT 1",
                (target,))
            row = cursor.fetchone()
            return dict(row) if row else None
