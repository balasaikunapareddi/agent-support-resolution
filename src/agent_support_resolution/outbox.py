"""Simulated send: an append-only outbox log.

Nothing in this repo sends real email. "Sending" appends the final text
to ``outbox.jsonl`` so demos and tests can verify exactly what would have
gone to the customer. Swap this class for a real ESP/CRM integration in
production — the graph only calls ``send()`` after the gate has passed.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .models import utc_now_iso


class Outbox:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def send(self, ticket_id: str, customer_id: str, text: str, sent_by: str) -> dict:
        record = {
            "ts": utc_now_iso(),
            "ticket_id": ticket_id,
            "customer_id": customer_id,
            "text": text,
            "sent_by": sent_by,  # "auto" or the reviewer's name
            "simulated": True,
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(l) for l in lines if l.strip()]
