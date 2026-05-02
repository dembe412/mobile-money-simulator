from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Checkpoint:
    """
    Checkpoint state:
      - balance includes all events up to last_event_id
      - last_event_id is the highest applied global event id
    """

    balance: float = 0.0
    last_event_id: int = 0

    def update(self, balance: float, last_event_id: int) -> None:
        self.balance = balance
        self.last_event_id = last_event_id
