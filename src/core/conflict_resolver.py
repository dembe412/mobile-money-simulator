"""
Conflict resolution for distributed operations
Detects and resolves conflicts in eventual consistency system
"""
from typing import Dict, Tuple, Optional
from datetime import datetime
from decimal import Decimal
import logging

from src.core.events import Event, EventType
from src.distributed.vector_clock import VectorClock

logger = logging.getLogger(__name__)


class ConflictResolutionStrategy:
    """Base class for conflict resolution strategies"""
    
    def resolve(self, event1: Event, event2: Event, account_balance: Decimal) -> Event:
        """Resolve conflict between two events"""
        raise NotImplementedError


class LastWriteWinsStrategy(ConflictResolutionStrategy):
    """
    Last-Write-Wins (LWW) conflict resolution
    
    Uses timestamp + server_id as tiebreaker to deterministically resolve conflicts
    Advantages: Simple, deterministic, no data loss (both operations recorded)
    Disadvantage: May not reflect actual business intent
    """
    
    def resolve(self, event1: Event, event2: Event, account_balance: Decimal) -> Event:
        """
        Resolve by keeping the event with later timestamp
        If timestamps are equal, use server_id as tiebreaker
        
        Args:
            event1: First event
            event2: Second event
            account_balance: Current account balance
            
        Returns:
            The "winning" event to apply
        """
        # Compare timestamps
        if event1.timestamp > event2.timestamp:
            winning = event1
            losing = event2
        elif event2.timestamp > event1.timestamp:
            winning = event2
            losing = event1
        else:
            # Timestamps equal, use server_id as tiebreaker (lexicographic order)
            if event1.server_id > event2.server_id:
                winning = event1
                losing = event2
            else:
                winning = event2
                losing = event1
        
        logger.info(f"LWW: Selected {winning.event_id} (timestamp={winning.timestamp}) "
                   f"over {losing.event_id} (timestamp={losing.timestamp})")
        
        return winning


class CompensationStrategy(ConflictResolutionStrategy):
    """
    Compensation strategy for transfer conflicts
    
    If transfer splits (source debits but destination doesn't credit):
    1. Record both sides in event log (immutable)
    2. Reverse the losing side with compensating transaction
    3. Update balance accordingly
    """
    
    def resolve(self, event1: Event, event2: Event, account_balance: Decimal) -> Event:
        """Resolve transfer split by compensating"""
        # Check if this is a transfer split
        if event1.event_type == EventType.TRANSFER_OUT and \
           event2.event_type != EventType.TRANSFER_IN:
            # event1 is transfer_out without matching transfer_in
            # Reverse it
            logger.warning(f"Transfer split detected: {event1.event_id} without matching IN")
            return event2  # Keep the other event, ignore the split
        
        elif event2.event_type == EventType.TRANSFER_OUT and \
             event1.event_type != EventType.TRANSFER_IN:
            # event2 is transfer_out without matching transfer_in
            logger.warning(f"Transfer split detected: {event2.event_id} without matching IN")
            return event1  # Keep the other event, ignore the split
        
        # Default to LWW
        return LastWriteWinsStrategy().resolve(event1, event2, account_balance)


class OperationTypeStrategy(ConflictResolutionStrategy):
    """
    Resolution based on operation types
    
    Priority: TRANSFER > WITHDRAW > DEPOSIT
    More critical operations take precedence
    """
    
    def resolve(self, event1: Event, event2: Event, account_balance: Decimal) -> Event:
        """Resolve by operation type priority"""
        priority = {
            EventType.TRANSFER_OUT: 3,
            EventType.TRANSFER_IN: 3,
            EventType.WITHDRAW: 2,
            EventType.DEPOSIT: 1,
        }
        
        p1 = priority.get(event1.event_type, 0)
        p2 = priority.get(event2.event_type, 0)
        
        if p1 > p2:
            logger.info(f"Operation priority: {event1.event_type} (p={p1}) "
                       f"selected over {event2.event_type} (p={p2})")
            return event1
        elif p2 > p1:
            logger.info(f"Operation priority: {event2.event_type} (p={p2}) "
                       f"selected over {event1.event_type} (p={p1})")
            return event2
        else:
            # Same priority, use LWW
            return LastWriteWinsStrategy().resolve(event1, event2, account_balance)


class ConflictResolver:
    """
    Main conflict resolution orchestrator
    Detects and resolves conflicts using configured strategies
    """
    
    def __init__(self):
        """Initialize conflict resolver"""
        self.strategy = LastWriteWinsStrategy()  # Default strategy
        self.conflict_history: Dict[str, Dict] = {}  # Log of resolved conflicts
    
    def set_strategy(self, strategy: ConflictResolutionStrategy):
        """Change resolution strategy"""
        self.strategy = strategy
        logger.info(f"Resolution strategy changed to {strategy.__class__.__name__}")
    
    def detect_balance_conflict(
        self,
        expected_balance: Decimal,
        actual_balance: Decimal,
        account_id: int
    ) -> Tuple[bool, str]:
        """
        Detect balance conflicts
        
        Args:
            expected_balance: What we expect based on events
            actual_balance: What we observe
            account_id: Account ID
            
        Returns:
            (is_conflict, description)
        """
        if expected_balance != actual_balance:
            diff = actual_balance - expected_balance
            return True, (f"Balance mismatch on account {account_id}: "
                         f"expected {expected_balance}, got {actual_balance} "
                         f"(diff: {diff})")
        return False, ""
    
    def resolve_balance_conflict(
        self,
        account_id: int,
        conflicting_events: list,
        current_balance: Decimal
    ) -> Decimal:
        """
        Resolve balance conflict by selecting authoritative event
        
        Args:
            account_id: Account with conflict
            conflicting_events: Events that caused conflict
            current_balance: Current observed balance
            
        Returns:
            Corrected balance
        """
        if len(conflicting_events) < 2:
            return current_balance
        
        # Sort by timestamp
        sorted_events = sorted(
            conflicting_events,
            key=lambda e: (e.timestamp, e.server_id)
        )
        
        # Take the winning event's balance
        winning_event = sorted_events[-1]
        resolved_balance = winning_event.balance_after
        
        logger.warning(
            f"Resolved balance conflict on account {account_id}: "
            f"{current_balance} → {resolved_balance} "
            f"(selected event: {winning_event.event_id})"
        )
        
        self.conflict_history[str(account_id)] = {
            'timestamp': datetime.utcnow().isoformat(),
            'conflicting_events': [e.event_id for e in conflicting_events],
            'winning_event': winning_event.event_id,
            'original_balance': str(current_balance),
            'corrected_balance': str(resolved_balance),
        }
        
        return resolved_balance
    
    def detect_lost_debit(
        self,
        account_id: int,
        events: list
    ) -> Tuple[bool, str]:
        """
        Detect if debit operation was lost during replication
        
        Example: Server A debits account, but Server B never gets the event
        
        Args:
            account_id: Account to check
            events: List of events for account
            
        Returns:
            (is_lost, description)
        """
        if not events:
            return False, ""
        
        # Check if we have matching debit/credit pairs
        debits = [e for e in events if e.event_type in [EventType.WITHDRAW, EventType.TRANSFER_OUT]]
        credits = [e for e in events if e.event_type in [EventType.DEPOSIT, EventType.TRANSFER_IN]]
        
        if len(debits) > len(credits):
            return True, f"More debits ({len(debits)}) than credits ({len(credits)}) on account {account_id}"
        
        return False, ""
    
    def detect_overdraft(
        self,
        account_id: int,
        balance_before: Decimal,
        amount: Decimal
    ) -> Tuple[bool, str]:
        """
        Detect if operation would cause overdraft
        
        Args:
            account_id: Account
            balance_before: Balance before operation
            amount: Amount to debit
            
        Returns:
            (would_overdraft, description)
        """
        if balance_before < amount:
            return True, (f"Overdraft on account {account_id}: "
                         f"balance {balance_before} < amount {amount}")
        return False, ""
    
    def get_conflict_log(self) -> Dict:
        """Get log of all resolved conflicts"""
        return self.conflict_history.copy()
    
    def __repr__(self):
        return f"ConflictResolver(strategy={self.strategy.__class__.__name__})"
