"""
Vector Clock implementation for causal ordering in distributed systems
Detects concurrent operations and enforces causality ordering
"""
from typing import Dict, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EventOrder(str, Enum):
    """Relationship between two events based on vector clocks"""
    BEFORE = "before"  # event1 happened before event2
    AFTER = "after"    # event1 happened after event2
    CONCURRENT = "concurrent"  # events happened concurrently (no causality)
    EQUAL = "equal"    # events are identical


class VectorClock:
    """
    Vector Clock for tracking causal ordering in distributed systems
    
    A vector clock is a dict mapping server_id → sequence_number
    Used to:
    1. Detect concurrent operations (conflicts)
    2. Enforce causal ordering
    3. Detect lost messages
    
    Example:
        server_1: [1, 0, 0]  (server_1 has seen 1 event from itself, 0 from others)
        server_2: [1, 1, 0]  (server_2 has seen 1 event from server_1, 1 from itself)
    """
    
    def __init__(self, server_ids: list = None, clock: Dict[str, int] = None):
        """
        Initialize vector clock
        
        Args:
            server_ids: List of all server IDs in system
            clock: Existing clock dict (for deserialization)
        """
        if clock:
            self.clock = clock.copy()
        elif server_ids:
            self.clock = {sid: 0 for sid in server_ids}
        else:
            self.clock = {}
    
    def increment(self, server_id: str):
        """
        Increment clock for this server (called after event generated)
        
        Args:
            server_id: Server that generated event
        """
        if server_id not in self.clock:
            self.clock[server_id] = 0
        self.clock[server_id] += 1
        logger.debug(f"Incremented clock for {server_id}: {self.clock}")
    
    def update(self, remote_clock: Dict[str, int]):
        """
        Update clock from received event (merge remote clock)
        Called when receiving event from peer
        
        Args:
            remote_clock: Vector clock from remote event
        """
        for server_id, remote_version in remote_clock.items():
            local_version = self.clock.get(server_id, 0)
            self.clock[server_id] = max(local_version, remote_version)
        logger.debug(f"Updated clock from remote: {self.clock}")
    
    def happens_before(self, other: 'VectorClock') -> bool:
        """
        Check if this event happened strictly before another
        
        Rules:
        - self ≤ other if for all servers: self[s] ≤ other[s]
        - self < other if self ≤ other AND self ≠ other
        
        Args:
            other: Another VectorClock to compare
            
        Returns:
            True if this strictly happened before other
            
        Example:
            self:  {s1: 1, s2: 0, s3: 0}
            other: {s1: 2, s2: 1, s3: 0}
            → True (self happened before other)
        """
        all_servers = set(self.clock.keys()) | set(other.clock.keys())
        
        # Check if self ≤ other (less than or equal)
        self_le_other = all(
            self.clock.get(sid, 0) <= other.clock.get(sid, 0)
            for sid in all_servers
        )
        
        # Check if they're equal
        is_equal = self.equals(other)
        
        # happens_before = ≤ AND ≠
        return self_le_other and not is_equal
    
    def concurrent(self, other: 'VectorClock') -> bool:
        """
        Check if events are concurrent (happened independently)
        
        Events are concurrent if neither happened before the other
        
        Args:
            other: Another VectorClock to compare
            
        Returns:
            True if events are concurrent
            
        Example:
            self:  {s1: 1, s2: 0, s3: 0}
            other: {s1: 0, s2: 1, s3: 0}
            → True (concurrent, neither happened before other)
        """
        return not self.happens_before(other) and not other.happens_before(self)
    
    def equals(self, other: 'VectorClock') -> bool:
        """
        Check if two clocks are identical
        
        Args:
            other: Another VectorClock to compare
            
        Returns:
            True if clocks are equal
        """
        all_servers = set(self.clock.keys()) | set(other.clock.keys())
        return all(
            self.clock.get(sid, 0) == other.clock.get(sid, 0)
            for sid in all_servers
        )
    
    def compare(self, other: 'VectorClock') -> EventOrder:
        """
        Compare two events and return their relationship
        
        Args:
            other: Another VectorClock to compare
            
        Returns:
            EventOrder: BEFORE, AFTER, CONCURRENT, or EQUAL
        """
        if self.equals(other):
            return EventOrder.EQUAL
        elif self.happens_before(other):
            return EventOrder.BEFORE
        elif other.happens_before(self):
            return EventOrder.AFTER
        else:
            return EventOrder.CONCURRENT
    
    def to_dict(self) -> Dict[str, int]:
        """Get clock as dictionary"""
        return self.clock.copy()
    
    def __repr__(self):
        return f"VectorClock({self.clock})"
    
    def __str__(self):
        return str(self.clock)


def detect_concurrent_operations(
    event1_clock: Dict[str, int],
    event2_clock: Dict[str, int],
    event1_account_id: int,
    event2_account_id: int
) -> Tuple[bool, str]:
    """
    Detect if two events are concurrent modifications on same account
    
    Used to identify conflicts that need resolution
    
    Args:
        event1_clock: Vector clock of first event
        event2_clock: Vector clock of second event
        event1_account_id: Account modified by event 1
        event2_account_id: Account modified by event 2
        
    Returns:
        (is_concurrent, description)
        
    Example:
        Both events modify account_1 concurrently → conflict detected
    """
    if event1_account_id != event2_account_id:
        return False, "Different accounts"
    
    vc1 = VectorClock(clock=event1_clock)
    vc2 = VectorClock(clock=event2_clock)
    
    if vc1.concurrent(vc2):
        return True, f"Concurrent operations on account {event1_account_id}"
    
    return False, "Operations have causal ordering"
