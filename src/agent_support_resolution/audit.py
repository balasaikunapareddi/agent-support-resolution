"""Append-only JSONL audit log.

Every state transition, tool call, policy decision, and human decision
for a ticket is one JSON line. Append-only and lock-guarded so concurrent
ticket processing cannot interleave partial writes. This is the record
you hand to compliance when someone asks "why did the bot send that?"
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .models import AuditEvent


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, ticket_id: str, event_type: str, node: str, detail: dict | None = None) -> AuditEvent:
        event = AuditEvent(
            ticket_id=ticket_id, event_type=event_type, node=node, detail=detail or {}
        )
        line = json.dumps(event.model_dump(), ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return event

    def events_for(self, ticket_id: str) -> list[AuditEvent]:
        if not self.path.exists():
            return []
        events: list[AuditEvent] = []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            event = AuditEvent(**json.loads(line))
            if event.ticket_id == ticket_id:
                events.append(event)
        return events

    def all_events(self) -> list[AuditEvent]:
        if not self.path.exists():
            return []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        return [AuditEvent(**json.loads(l)) for l in lines if l.strip()]
