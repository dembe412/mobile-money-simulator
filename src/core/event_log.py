"""
Event Log Implementation
Manages immutable events with efficient storage, deduplication, and querying
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional, Set
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of events in the system"""
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"


@dataclass
class TransactionEvent:
    """
    Immutable event representing a transaction.
    
    Critical properties:
    - event_id: Globally unique and ordered (monotonically increasing)
    - type: "deposit" or "withdraw"
    - amount: Transaction amount
    - timestamp: When event was created
    - node_id: Which node originated this event
    - is_applied: Whether this event has been applied to local state
    """
    event_id: int
    type: EventType
    amount: Decimal
    account_id: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    node_id: str = ""
    request_id: str = ""  # For idempotency
    is_applied: bool = False
    
    def to_dict(self) -> Dict:
        """Serialize event to dictionary"""
        return {
            "event_id": self.event_id,
            "type": self.type.value,
            "amount": str(self.amount),
            "account_id": self.account_id,
            "timestamp": self.timestamp.isoformat(),
            "node_id": self.node_id,
            "request_id": self.request_id,
            "is_applied": self.is_applied,
        }
    
    @staticmethod
    def from_dict(data: Dict) -> "TransactionEvent":
        """Deserialize event from dictionary"""
        return TransactionEvent(
            event_id=data["event_id"],
            type=EventType(data["type"]),
            amount=Decimal(data["amount"]),
            account_id=data["account_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            node_id=data.get("node_id", ""),
            request_id=data.get("request_id", ""),
            is_applied=data.get("is_applied", False),
        )
    
    def __repr__(self) -> str:
        return (
            f"Event(id={self.event_id}, type={self.type.value}, "
            f"amount={self.amount}, node={self.node_id})"
        )


class EventLog:
    """
    Manages all transaction events.
    
    Guarantees:
    - All events are immutable once added
    - Events are indexed by event_id for O(1) lookup
    - Deduplication: duplicate event_ids are rejected
    - Events are ordered by event_id
    """
    
    def __init__(self):
        """Initialize event log"""
        self.events: Dict[int, TransactionEvent] = {}  # event_id -> event
        self.max_event_id: int = 0
        self.seen_request_ids: Set[str] = set()  # For idempotency
    
    def add_event(self, event: TransactionEvent) -> bool:
        """
        Add event to log.
        
        Args:
            event: Event to add
            
        Returns:
            True if added, False if duplicate or invalid
        """
        # Check for duplicate event_id
        if event.event_id in self.events:
            logger.warning(
                f"Duplicate event rejected: event_id={event.event_id} "
                f"(already exists)"
            )
            return False
        
        # Check for duplicate request_id (idempotency)
        if event.request_id and event.request_id in self.seen_request_ids:
            logger.debug(
                f"Duplicate request rejected (idempotency): "
                f"request_id={event.request_id}"
            )
            return False
        
        # Add event to log
        self.events[event.event_id] = event
        if event.request_id:
            self.seen_request_ids.add(event.request_id)
        
        # Update max event id
        if event.event_id > self.max_event_id:
            self.max_event_id = event.event_id
        
        logger.debug(f"Event added: {event}")
        return True
    
    def add_events(self, events: List[TransactionEvent]) -> int:
        """
        Add multiple events to log.
        
        Args:
            events: List of events to add
            
        Returns:
            Number of events successfully added
        """
        count = 0
        for event in events:
            if self.add_event(event):
                count += 1
        logger.info(f"Added {count}/{len(events)} events to log")
        return count
    
    def get_event(self, event_id: int) -> Optional[TransactionEvent]:
        """
        Get event by ID.
        
        Args:
            event_id: Event ID
            
        Returns:
            Event if found, None otherwise
        """
        return self.events.get(event_id)
    
    def get_events_after(self, after_event_id: int) -> List[TransactionEvent]:
        """
        Get all events with event_id > after_event_id.
        
        This is used during sync to fetch only new events.
        
        Args:
            after_event_id: Return events after this ID
            
        Returns:
            List of events ordered by event_id
        """
        events = [
            event for event_id, event in self.events.items()
            if event_id > after_event_id
        ]
        # Sort by event_id to maintain order
        events.sort(key=lambda e: e.event_id)
        return events
    
    def get_all_events(self) -> List[TransactionEvent]:
        """
        Get all events in the log.
        
        Returns:
            List of events ordered by event_id
        """
        events = list(self.events.values())
        events.sort(key=lambda e: e.event_id)
        return events
    
    def get_events_by_type(self, event_type: EventType) -> List[TransactionEvent]:
        """
        Get all events of a specific type.
        
        Args:
            event_type: Type of event to filter by
            
        Returns:
            List of events of specified type, ordered by event_id
        """
        events = [e for e in self.events.values() if e.type == event_type]
        events.sort(key=lambda e: e.event_id)
        return events
    
    def merge_events(self, remote_events: List[TransactionEvent]) -> int:
        """
        Merge remote events into local log.
        
        Deduplication is automatic: if event_id already exists locally, it's skipped.
        
        Args:
            remote_events: Events from remote node
            
        Returns:
            Number of new events merged
        """
        new_count = 0
        for event in remote_events:
            if self.add_event(event):
                new_count += 1
        
        logger.info(
            f"Merged {new_count}/{len(remote_events)} remote events "
            f"(duplicates skipped)"
        )
        return new_count
    
    def compute_balance(self, checkpoint_balance: Decimal, checkpoint_event_id: int) -> Decimal:
        """
        Compute balance from checkpoint + subsequent events.
        
        This is the key optimization: instead of replaying all events from the beginning,
        we only replay events after the checkpoint.
        
        Formula:
            balance = checkpoint_balance + sum(events where event_id > checkpoint_event_id)
        
        Args:
            checkpoint_balance: Balance at checkpoint
            checkpoint_event_id: Last event ID in checkpoint
            
        Returns:
            Current balance
        """
        balance = checkpoint_balance
        subsequent_events = self.get_events_after(checkpoint_event_id)
        
        for event in subsequent_events:
            if event.type == EventType.DEPOSIT:
                balance += event.amount
            elif event.type == EventType.WITHDRAW:
                balance -= event.amount
        
        return balance
    
    def validate_consistency(self) -> bool:
        """
        Validate event log consistency.
        
        Checks:
        - All event IDs are unique
        - Events are properly formed
        
        Returns:
            True if consistent, False otherwise
        """
        if not self.events:
            return True
        
        seen_ids = set()
        for event_id, event in self.events.items():
            if event_id in seen_ids:
                logger.error(f"Duplicate event ID found: {event_id}")
                return False
            if event.event_id != event_id:
                logger.error(
                    f"Event ID mismatch: stored={event_id}, "
                    f"event.event_id={event.event_id}"
                )
                return False
            seen_ids.add(event_id)
        
        logger.debug("Event log consistency check passed")
        return True
    
    def __len__(self) -> int:
        """Return number of events in log"""
        return len(self.events)
    
    def __repr__(self) -> str:
        return f"EventLog(size={len(self.events)}, max_event_id={self.max_event_id})"
