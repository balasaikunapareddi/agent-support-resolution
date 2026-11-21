"""Human review queue (SQLite, thread-safe).

Tickets the gate will not auto-resolve land here with the draft (unless
policy hard-blocked it), the routing reasons, and status. The queue is
the worklist a support lead sees; approve/edit/reject decisions are
applied by ``SupportPipeline`` (graph.py), which resumes the paused
LangGraph thread. This module only persists queue state.

Thread-safety: one connection with ``check_same_thread=False`` guarded
by a lock — the graph may run tickets from multiple threads.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .models import ReviewError, ReviewItem, utc_now_iso


class ReviewQueue:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_items (
                    ticket_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    draft_text TEXT,
                    reasons TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    decided_by TEXT,
                    decided_at TEXT
                )
                """
            )
            self._conn.commit()

    def add(self, item: ReviewItem) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO review_items VALUES (?, ?, ?, ?, ?, ?, ?)",
                (item.ticket_id, item.status, item.draft_text,
                 json.dumps(item.reasons), item.created_at,
                 item.decided_by, item.decided_at),
            )
            self._conn.commit()

    def get(self, ticket_id: str) -> ReviewItem | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM review_items WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
        return self._to_item(row) if row else None

    def list_pending(self) -> list[ReviewItem]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM review_items WHERE status = 'pending' ORDER BY created_at"
            ).fetchall()
        return [self._to_item(r) for r in rows]

    def mark_decided(self, ticket_id: str, status: str, reviewer: str) -> ReviewItem:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE review_items SET status = ?, decided_by = ?, decided_at = ? "
                "WHERE ticket_id = ? AND status = 'pending'",
                (status, reviewer, utc_now_iso(), ticket_id),
            )
            self._conn.commit()
            if cur.rowcount == 0:
                raise ReviewError(
                    f"No pending review item for ticket {ticket_id} "
                    "(unknown id or already decided)."
                )
        item = self.get(ticket_id)
        assert item is not None
        return item

    @staticmethod
    def _to_item(row: sqlite3.Row) -> ReviewItem:
        return ReviewItem(
            ticket_id=row["ticket_id"],
            status=row["status"],
            draft_text=row["draft_text"],
            reasons=json.loads(row["reasons"]),
            created_at=row["created_at"],
            decided_by=row["decided_by"],
            decided_at=row["decided_at"],
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()
