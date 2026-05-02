from __future__ import annotations

import random
import threading
import time
from typing import Dict, List

from event_log import Event


class GlobalEventIDAllocator:
    """Thread-safe, strictly increasing global event ID generator."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_id = 1

    def next_id(self) -> int:
        with self._lock:
            eid = self._next_id
            self._next_id += 1
            return eid


class Network:
    """Simulated network with delay for sync and propagation."""

    def __init__(self, min_delay_ms: int = 10, max_delay_ms: int = 120) -> None:
        self.nodes: Dict[str, "Node"] = {}
        self.min_delay_ms = min_delay_ms
        self.max_delay_ms = max_delay_ms
        self.id_allocator = GlobalEventIDAllocator()

    def register_node(self, node: "Node") -> None:
        self.nodes[node.node_id] = node

    def peers_of(self, node_id: str) -> List["Node"]:
        return [n for nid, n in self.nodes.items() if nid != node_id]

    def next_event_id(self) -> int:
        return self.id_allocator.next_id()

    def network_delay(self) -> None:
        delay_ms = random.randint(self.min_delay_ms, self.max_delay_ms)
        time.sleep(delay_ms / 1000.0)

    def fetch_events_after(self, requester_id: str, target_id: str, after_event_id: int) -> List[Event]:
        self.network_delay()
        target = self.nodes[target_id]
        return target.get_events_after(after_event_id)

    def push_event(self, from_node: str, to_node: str, event: Event) -> bool:
        self.network_delay()
        return self.nodes[to_node].receive_event(event, source_node_id=from_node)
