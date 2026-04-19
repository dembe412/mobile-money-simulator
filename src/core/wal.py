"""
Write-Ahead Log (WAL) for durability and recovery
Events are written to WAL before being applied to ensure recovery on crash
"""
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class WALStatus(str, Enum):
    """Status of a WAL entry"""
    PENDING = "pending"  # Created, not yet applied
    APPLIED = "applied"  # Applied to local state
    REPLICATED = "replicated"  # Replicated to quorum


@dataclass
class LogEntry:
    """Entry in the write-ahead log"""
    log_id: int
    event_id: str
    status: WALStatus = WALStatus.PENDING
    replicated_count: int = 0  # how many peers have acked
    required_replicas: int = 1  # quorum size (usually 2/3)
    created_at: datetime = None
    applied_at: Optional[datetime] = None
    replicated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    def mark_applied(self):
        """Mark this entry as applied"""
        self.status = WALStatus.APPLIED
        self.applied_at = datetime.utcnow()
    
    def mark_replicated(self):
        """Mark this entry as replicated"""
        self.status = WALStatus.REPLICATED
        self.replicated_at = datetime.utcnow()
    
    def increment_replica_ack(self):
        """Increment count of replicas that acked"""
        self.replicated_count += 1
    
    def is_quorum_reached(self) -> bool:
        """Check if quorum has been reached"""
        return self.replicated_count >= self.required_replicas
    
    def __repr__(self):
        return (f"LogEntry(log_id={self.log_id}, event_id={self.event_id}, "
                f"status={self.status.value}, replicated={self.replicated_count}/{self.required_replicas})")


class WriteAheadLog:
    """
    Write-ahead log for durability
    
    Operations:
    1. Event generated
    2. LogEntry appended to WAL (disk persist)
    3. Event applied to Account state (in-memory)
    4. Event marked as applied in WAL
    5. Event replicated to peers
    6. Replication acks received
    7. Event marked as replicated in WAL
    
    On restart: replay all entries with status != REPLICATED
    """
    
    def __init__(self):
        """Initialize write-ahead log"""
        self.log_entries: Dict[str, LogEntry] = {}  # event_id -> LogEntry
        self.pending_entries: List[str] = []  # event_ids in PENDING status
        self.applied_entries: List[str] = []  # event_ids in APPLIED status
        self.replicated_entries: List[str] = []  # event_ids in REPLICATED status
        self.next_log_id = 1
    
    def append(self, event_id: str, required_replicas: int = 1) -> int:
        """
        Append entry to WAL
        
        Args:
            event_id: Event ID to track
            required_replicas: Quorum size for this event
            
        Returns:
            log_id assigned to this entry
        """
        log_id = self.next_log_id
        self.next_log_id += 1
        
        entry = LogEntry(
            log_id=log_id,
            event_id=event_id,
            status=WALStatus.PENDING,
            required_replicas=required_replicas,
        )
        
        self.log_entries[event_id] = entry
        self.pending_entries.append(event_id)
        
        logger.debug(f"WAL entry appended: {entry}")
        return log_id
    
    def get_entry(self, event_id: str) -> Optional[LogEntry]:
        """Get log entry for an event"""
        return self.log_entries.get(event_id)
    
    def mark_applied(self, event_id: str) -> bool:
        """
        Mark log entry as applied
        
        Args:
            event_id: Event to mark applied
            
        Returns:
            True if marked successfully
        """
        if event_id not in self.log_entries:
            logger.warning(f"WAL entry not found for event {event_id}")
            return False
        
        entry = self.log_entries[event_id]
        entry.mark_applied()
        
        # Move to applied list
        if event_id in self.pending_entries:
            self.pending_entries.remove(event_id)
        self.applied_entries.append(event_id)
        
        logger.debug(f"WAL entry marked applied: {entry}")
        return True
    
    def mark_replica_ack(self, event_id: str) -> bool:
        """
        Mark that a replica acked this event
        
        Args:
            event_id: Event that was acked
            
        Returns:
            True if quorum reached after this ack
        """
        if event_id not in self.log_entries:
            return False
        
        entry = self.log_entries[event_id]
        entry.increment_replica_ack()
        
        # Check if quorum reached
        if entry.is_quorum_reached():
            self.mark_replicated(event_id)
            return True
        
        return False
    
    def mark_replicated(self, event_id: str) -> bool:
        """
        Mark log entry as replicated
        
        Args:
            event_id: Event to mark replicated
            
        Returns:
            True if marked successfully
        """
        if event_id not in self.log_entries:
            return False
        
        entry = self.log_entries[event_id]
        entry.mark_replicated()
        
        # Move to replicated list
        if event_id in self.applied_entries:
            self.applied_entries.remove(event_id)
        self.replicated_entries.append(event_id)
        
        logger.debug(f"WAL entry marked replicated: {entry}")
        return True
    
    def get_pending_entries(self) -> List[LogEntry]:
        """Get all pending entries (not yet applied)"""
        return [self.log_entries[eid] for eid in self.pending_entries 
                if eid in self.log_entries]
    
    def get_applied_entries(self) -> List[LogEntry]:
        """Get all applied entries (applied but not yet replicated)"""
        return [self.log_entries[eid] for eid in self.applied_entries 
                if eid in self.log_entries]
    
    def get_replicated_entries(self) -> List[LogEntry]:
        """Get all replicated entries"""
        return [self.log_entries[eid] for eid in self.replicated_entries 
                if eid in self.log_entries]
    
    def get_unapplied_events(self) -> List[str]:
        """Get event IDs that need to be applied on restart (recovery)"""
        return self.pending_entries.copy()
    
    def get_unreplicated_events(self) -> List[str]:
        """Get event IDs that need replication"""
        return (self.pending_entries + self.applied_entries).copy()
    
    def get_stats(self) -> Dict:
        """Get WAL statistics"""
        return {
            'total_entries': len(self.log_entries),
            'pending': len(self.pending_entries),
            'applied': len(self.applied_entries),
            'replicated': len(self.replicated_entries),
            'next_log_id': self.next_log_id,
        }
    
    def __repr__(self):
        return (f"WriteAheadLog(total={len(self.log_entries)}, "
                f"pending={len(self.pending_entries)}, "
                f"applied={len(self.applied_entries)}, "
                f"replicated={len(self.replicated_entries)})")
