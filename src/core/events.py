"""
Event sourcing implementation
All operations are recorded as immutable events
Events are the source of truth; Account state is derived from events
"""
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from decimal import Decimal
import uuid
import logging

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of events in the system"""
    WITHDRAW = "withdraw"
    DEPOSIT = "deposit"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    ACCOUNT_CREATED = "account_created"


class EventStatus(str, Enum):
    """Status of event in replication pipeline"""
    PENDING = "pending"  # Created, not yet applied locally
    APPLIED = "applied"  # Applied to local account state
    REPLICATED = "replicated"  # Replicated to quorum of peers


@dataclass
class Event:
    """Immutable event representing a state change"""
    event_id: str  # Unique identifier (UUID)
    event_type: EventType
    account_id: int
    request_id: str  # For idempotency
    amount: Optional[Decimal] = None
    balance_before: Optional[Decimal] = None
    balance_after: Optional[Decimal] = None
    # Optional account metadata to carry with events
    phone_number: Optional[str] = None
    account_holder_name: Optional[str] = None
    
    # Causality tracking
    vector_clock: Dict[str, int] = None
    
    # Metadata
    server_id: str = None  # Which server created this event
    timestamp: datetime = None
    client_reference: Optional[str] = None
    
    # Replication state
    is_applied: bool = False
    is_replicated: bool = False
    replicated_to: Dict[str, datetime] = None  # {server_id: ack_timestamp}
    
    created_at: datetime = None
    
    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.utcnow()
        if not self.created_at:
            self.created_at = datetime.utcnow()
        if self.vector_clock is None:
            self.vector_clock = {}
        if self.replicated_to is None:
            self.replicated_to = {}
    
    def to_dict(self) -> Dict:
        """Convert event to dictionary for storage/serialization"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type.value,
            'account_id': self.account_id,
            'request_id': self.request_id,
            'amount': str(self.amount) if self.amount else None,
            'balance_before': str(self.balance_before) if self.balance_before else None,
            'balance_after': str(self.balance_after) if self.balance_after else None,
            'vector_clock': self.vector_clock,
            'server_id': self.server_id,
            'timestamp': self.timestamp.isoformat(),
            'client_reference': self.client_reference,
            'is_applied': self.is_applied,
            'is_replicated': self.is_replicated,
            'replicated_to': {k: v.isoformat() if isinstance(v, datetime) else v 
                             for k, v in (self.replicated_to or {}).items()},
            'phone_number': self.phone_number,
            'account_holder_name': self.account_holder_name,
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'Event':
        """Create event from dictionary (deserialization)"""
        amount = Decimal(data['amount']) if data.get('amount') else None
        balance_before = Decimal(data['balance_before']) if data.get('balance_before') else None
        balance_after = Decimal(data['balance_after']) if data.get('balance_after') else None
        
        return Event(
            event_id=data['event_id'],
            event_type=EventType(data['event_type']),
            account_id=data['account_id'],
            request_id=data['request_id'],
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            vector_clock=data.get('vector_clock', {}),
            server_id=data.get('server_id'),
            timestamp=datetime.fromisoformat(data['timestamp']) if data.get('timestamp') else None,
            client_reference=data.get('client_reference'),
            is_applied=data.get('is_applied', False),
            is_replicated=data.get('is_replicated', False),
            replicated_to=data.get('replicated_to', {}),
            phone_number=data.get('phone_number'),
            account_holder_name=data.get('account_holder_name'),
        )
    
    def __repr__(self):
        return (f"Event({self.event_id}, {self.event_type.value}, "
                f"account={self.account_id}, request={self.request_id}, "
                f"amount={self.amount})")


class EventStore:
    """
    In-memory event store for managing events
    In production, events are persisted in database
    """
    
    def __init__(self):
        """Initialize event store"""
        self.events: Dict[str, Event] = {}  # event_id -> Event
        self.account_events: Dict[int, List[str]] = {}  # account_id -> [event_ids]
        self.unapplied_events: List[str] = []  # event_ids pending application
    
    def append(self, event: Event) -> str:
        """
        Append event to store
        
        Args:
            event: Event to append
            
        Returns:
            event_id
        """
        self.events[event.event_id] = event
        
        # Track by account
        if event.account_id not in self.account_events:
            self.account_events[event.account_id] = []
        self.account_events[event.account_id].append(event.event_id)
        
        # Track as unapplied
        if not event.is_applied:
            self.unapplied_events.append(event.event_id)
        
        logger.debug(f"Event appended: {event.event_id}")
        return event.event_id
    
    def get_event(self, event_id: str) -> Optional[Event]:
        """Get event by ID"""
        return self.events.get(event_id)
    
    def get_account_events(self, account_id: int) -> List[Event]:
        """Get all events for an account"""
        event_ids = self.account_events.get(account_id, [])
        return [self.events[eid] for eid in event_ids if eid in self.events]
    
    def mark_applied(self, event_id: str) -> bool:
        """Mark event as applied to local state"""
        if event_id in self.events:
            self.events[event_id].is_applied = True
            if event_id in self.unapplied_events:
                self.unapplied_events.remove(event_id)
            return True
        return False
    
    def mark_replicated(self, event_id: str, server_id: str) -> bool:
        """Mark event as replicated to peer"""
        if event_id in self.events:
            event = self.events[event_id]
            if event.replicated_to is None:
                event.replicated_to = {}
            event.replicated_to[server_id] = datetime.utcnow()
            
            # Mark fully replicated if acked by all peers
            # (In real system, this would be checked against quorum)
            event.is_replicated = True
            return True
        return False
    
    def get_unapplied_events(self) -> List[Event]:
        """Get all events pending application"""
        return [self.events[eid] for eid in self.unapplied_events 
                if eid in self.events]
    
    def get_unapplied_event_ids(self) -> List[str]:
        """Get IDs of unapplied events"""
        return self.unapplied_events.copy()
    
    def get_unreplicated_events(self, server_id: Optional[str] = None) -> List[Event]:
        """
        Get events not yet replicated
        
        Args:
            server_id: If provided, get events not yet acked by this peer
            
        Returns:
            List of unreplicated events
        """
        if server_id:
            return [e for e in self.events.values() 
                   if not e.is_replicated or server_id not in (e.replicated_to or {})]
        return [e for e in self.events.values() if not e.is_replicated]
    
    def all_events(self) -> List[Event]:
        """Get all events in store"""
        return list(self.events.values())
    
    def event_count(self) -> int:
        """Get total event count"""
        return len(self.events)
    
    def unapplied_count(self) -> int:
        """Get count of unapplied events"""
        return len(self.unapplied_events)
    
    def get_stats(self) -> Dict:
        """Get event store statistics"""
        return {
            'total_events': len(self.events),
            'unapplied_events': len(self.unapplied_events),
            'accounts': len(self.account_events),
            'replicated_events': sum(1 for e in self.events.values() if e.is_replicated),
        }


def create_withdraw_event(
    account_id: int,
    request_id: str,
    amount: Decimal,
    balance_before: Decimal,
    balance_after: Decimal,
    server_id: str,
    vector_clock: Dict[str, int],
    client_reference: Optional[str] = None,
    phone_number: Optional[str] = None,
    account_holder_name: Optional[str] = None,
) -> Event:
    """Factory function to create withdraw event"""
    return Event(
        event_id=str(uuid.uuid4()),
        event_type=EventType.WITHDRAW,
        account_id=account_id,
        request_id=request_id,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        vector_clock=vector_clock,
        server_id=server_id,
        timestamp=datetime.utcnow(),
        client_reference=client_reference,
        phone_number=phone_number,
        account_holder_name=account_holder_name,
    )


def create_deposit_event(
    account_id: int,
    request_id: str,
    amount: Decimal,
    balance_before: Decimal,
    balance_after: Decimal,
    server_id: str,
    vector_clock: Dict[str, int],
    client_reference: Optional[str] = None,
    phone_number: Optional[str] = None,
    account_holder_name: Optional[str] = None,
) -> Event:
    """Factory function to create deposit event"""
    return Event(
        event_id=str(uuid.uuid4()),
        event_type=EventType.DEPOSIT,
        account_id=account_id,
        request_id=request_id,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        vector_clock=vector_clock,
        server_id=server_id,
        timestamp=datetime.utcnow(),
        client_reference=client_reference,
        phone_number=phone_number,
        account_holder_name=account_holder_name,
    )


def create_transfer_out_event(
    account_id: int,
    request_id: str,
    amount: Decimal,
    balance_before: Decimal,
    balance_after: Decimal,
    server_id: str,
    vector_clock: Dict[str, int],
    client_reference: Optional[str] = None,
    phone_number: Optional[str] = None,
    account_holder_name: Optional[str] = None,
) -> Event:
    """Factory function to create transfer out event"""
    return Event(
        event_id=str(uuid.uuid4()),
        event_type=EventType.TRANSFER_OUT,
        account_id=account_id,
        request_id=request_id,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        vector_clock=vector_clock,
        server_id=server_id,
        timestamp=datetime.utcnow(),
        client_reference=client_reference,
        phone_number=phone_number,
        account_holder_name=account_holder_name,
    )


def create_transfer_in_event(
    account_id: int,
    request_id: str,
    amount: Decimal,
    balance_before: Decimal,
    balance_after: Decimal,
    server_id: str,
    vector_clock: Dict[str, int],
    client_reference: Optional[str] = None,
    phone_number: Optional[str] = None,
    account_holder_name: Optional[str] = None,
) -> Event:
    """Factory function to create transfer in event"""
    return Event(
        event_id=str(uuid.uuid4()),
        event_type=EventType.TRANSFER_IN,
        account_id=account_id,
        request_id=request_id,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        vector_clock=vector_clock,
        server_id=server_id,
        timestamp=datetime.utcnow(),
        client_reference=client_reference,
        phone_number=phone_number,
        account_holder_name=account_holder_name,
    )


def create_account_created_event(
    account_id: int,
    request_id: str,
    initial_balance: Decimal,
    server_id: str,
    vector_clock: Dict[str, int],
    client_reference: Optional[str] = None,
    phone_number: Optional[str] = None,
    account_holder_name: Optional[str] = None,
) -> Event:
    """Factory function to create account-created event."""
    return Event(
        event_id=str(uuid.uuid4()),
        event_type=EventType.ACCOUNT_CREATED,
        account_id=account_id,
        request_id=request_id,
        amount=initial_balance,
        balance_before=Decimal(0),
        balance_after=initial_balance,
        vector_clock=vector_clock,
        server_id=server_id,
        timestamp=datetime.utcnow(),
        client_reference=client_reference,
        phone_number=phone_number,
        account_holder_name=account_holder_name,
    )
