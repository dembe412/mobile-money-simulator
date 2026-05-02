from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Event:
    """Immutable event (source of truth)."""

    event_id: int
    type: str  # "deposit" | "withdraw"
    amount: float  # deposit > 0, withdraw < 0
    timestamp: str
    node_id: str
    request_id: str


class EventLog:
    """Node-local event log with deduplication and ordered reads."""

    def __init__(self) -> None:
        self._events_by_id: Dict[int, Event] = {}
        self._event_id_by_request: Dict[str, int] = {}

    def add_event(self, event: Event) -> bool:
        """
        Add a new event idempotently.
        Returns False if duplicate event_id or duplicate request_id.
        """
        if event.event_id in self._events_by_id:
            return False
        if event.request_id and event.request_id in self._event_id_by_request:
            return False

        self._events_by_id[event.event_id] = event
        if event.request_id:
            self._event_id_by_request[event.request_id] = event.event_id
        return True

    def get_events_after(self, event_id: int) -> List[Event]:
        out = [e for eid, e in self._events_by_id.items() if eid > event_id]
        out.sort(key=lambda e: e.event_id)
        return out

    def has_event(self, event_id: int) -> bool:
        return event_id in self._events_by_id

    def get_event(self, event_id: int) -> Optional[Event]:
        return self._events_by_id.get(event_id)

    def all_events(self) -> List[Event]:
        out = list(self._events_by_id.values())
        out.sort(key=lambda e: e.event_id)
        return out

    def event_count(self) -> int:
        return len(self._events_by_id)

    @staticmethod
    def now_iso() -> str:
        return datetime.utcnow().isoformat()
