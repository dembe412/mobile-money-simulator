from __future__ import annotations

import threading
from typing import Iterable, List, Optional

from checkpoint import Checkpoint
from event_log import Event, EventLog


class Node:
    """Distributed node with event log + checkpoint."""

    def __init__(self, node_id: str, network: "Network", initial_balance: float = 0.0) -> None:
        self.node_id = node_id
        self.network = network
        self.event_log = EventLog()
        self.checkpoint = Checkpoint(balance=initial_balance, last_event_id=0)
        self._withdraw_lock = threading.Lock()  # serialize withdrawals on this node
        self.network.register_node(self)

    # -----------------------------
    # Event and state helpers
    # -----------------------------
    def _new_event(self, event_type: str, amount: float, request_id: str) -> Event:
        return Event(
            event_id=self.network.next_event_id(),
            type=event_type,
            amount=amount,
            timestamp=EventLog.now_iso(),
            node_id=self.node_id,
            request_id=request_id,
        )

    def _apply_events_to_checkpoint(self, events: Iterable[Event]) -> None:
        # Ensure events are present in the log first.
        for event in events:
            if not self.event_log.has_event(event.event_id):
                self.event_log.add_event(event)

        # Advance checkpoint only through contiguous event IDs.
        bal = self.checkpoint.balance
        last = self.checkpoint.last_event_id
        while True:
            next_id = last + 1
            next_event = self.event_log.get_event(next_id)
            if not next_event:
                break
            bal += next_event.amount
            last = next_id

        if last > self.checkpoint.last_event_id:
            self.checkpoint.update(balance=bal, last_event_id=last)

    def recompute_from_checkpoint(self) -> float:
        new_events = self.event_log.get_events_after(self.checkpoint.last_event_id)
        self._apply_events_to_checkpoint(new_events)
        return self.checkpoint.balance

    # -----------------------------
    # Public API
    # -----------------------------
    def deposit(self, amount: float, request_id: str) -> bool:
        """
        Deposits are local-only (eventually consistent).
        They are NOT immediately propagated.
        """
        if amount <= 0:
            return False
        event = self._new_event("deposit", amount, request_id=request_id)
        ok = self.event_log.add_event(event)
        if not ok:
            return False

        # local apply only
        self._apply_events_to_checkpoint([event])
        print(
            f"[{self.node_id}] DEPOSIT local event={event.event_id} "
            f"amount={amount:.2f} balance={self.checkpoint.balance:.2f}"
        )
        return True

    def get_events_after(self, event_id: int) -> List[Event]:
        return self.event_log.get_events_after(event_id)

    def receive_event(self, event: Event, source_node_id: str = "") -> bool:
        """
        Receives propagated events from peer.
        Idempotent due to event_id/request_id dedupe.
        """
        added = self.event_log.add_event(event)
        if not added:
            return False

        # Apply if contiguous; otherwise keep in log until sync fills gaps.
        self._apply_events_to_checkpoint([event])

        print(
            f"[{self.node_id}] RECEIVE from={source_node_id or event.node_id} "
            f"event={event.event_id} type={event.type} amount={event.amount:.2f}"
        )
        return True

    def merge_events(self, events: Iterable[Event]) -> int:
        merged = 0
        new_events = []
        for event in sorted(events, key=lambda e: e.event_id):
            if self.event_log.add_event(event):
                merged += 1
                new_events.append(event)

        self._apply_events_to_checkpoint(new_events)
        if merged:
            print(
                f"[{self.node_id}] MERGE merged={merged} "
                f"last_event_id={self.checkpoint.last_event_id} "
                f"balance={self.checkpoint.balance:.2f}"
            )
        return merged

    def sync_with_node(self, peer_node_id: str) -> int:
        """
        Fetch events where event_id > checkpoint.last_event_id from one peer.
        """
        missing = self.network.fetch_events_after(
            requester_id=self.node_id,
            target_id=peer_node_id,
            after_event_id=self.checkpoint.last_event_id,
        )
        if missing:
            print(
                f"[{self.node_id}] SYNC from={peer_node_id} "
                f"fetched={len(missing)} after={self.checkpoint.last_event_id}"
            )
        return self.merge_events(missing)

    def sync_all(self) -> int:
        total = 0
        for peer in self.network.peers_of(self.node_id):
            total += self.sync_with_node(peer.node_id)
        return total

    def withdraw(self, withdraw_amount: float, request_id: str) -> bool:
        """
        Strongly-consistent withdrawal sequence:
          1) Sync all missing events
          2) Merge + dedupe + order
          3) Recompute balance
          4) Validate
          5) Serialize via lock
          6) Create withdrawal event
          7) Update checkpoint
          8) Immediately propagate to all peers
        """
        if withdraw_amount <= 0:
            return False

        with self._withdraw_lock:
            self.sync_all()
            current_balance = self.recompute_from_checkpoint()

            if current_balance < withdraw_amount:
                print(
                    f"[{self.node_id}] WITHDRAW REJECTED amount={withdraw_amount:.2f} "
                    f"balance={current_balance:.2f}"
                )
                return False

            event = self._new_event("withdraw", -withdraw_amount, request_id=request_id)
            if not self.event_log.add_event(event):
                return False

            self._apply_events_to_checkpoint([event])
            print(
                f"[{self.node_id}] WITHDRAW COMMIT event={event.event_id} "
                f"amount={withdraw_amount:.2f} balance={self.checkpoint.balance:.2f}"
            )

            propagated = 0
            for peer in self.network.peers_of(self.node_id):
                if self.network.push_event(self.node_id, peer.node_id, event):
                    propagated += 1
            print(
                f"[{self.node_id}] WITHDRAW PROPAGATED event={event.event_id} "
                f"to={propagated}/{len(self.network.peers_of(self.node_id))}"
            )
            return True
