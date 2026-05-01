"""
Checkpoint System for Event Sourcing
Tracks processed balance and last event ID to minimize recomputation
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """
    Represents a stable point in event history.
    The balance field represents the computed balance after processing all events up to last_event_id.
    
    This enables efficient state recovery and reduces bandwidth by only syncing events
    after this checkpoint.
    """
    balance: Decimal
    last_event_id: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    node_id: str = ""
    account_id: int = 0
    
    # Metadata for checkpoint verification
    total_deposits: Decimal = Decimal(0)
    total_withdrawals: Decimal = Decimal(0)
    event_count: int = 0
    
    def to_dict(self) -> Dict:
        """Serialize checkpoint to dictionary"""
        return {
            "balance": str(self.balance),
            "last_event_id": self.last_event_id,
            "timestamp": self.timestamp.isoformat(),
            "node_id": self.node_id,
            "account_id": self.account_id,
            "total_deposits": str(self.total_deposits),
            "total_withdrawals": str(self.total_withdrawals),
            "event_count": self.event_count,
        }
    
    @staticmethod
    def from_dict(data: Dict) -> "Checkpoint":
        """Deserialize checkpoint from dictionary"""
        return Checkpoint(
            balance=Decimal(data["balance"]),
            last_event_id=data["last_event_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            node_id=data.get("node_id", ""),
            account_id=data.get("account_id", 0),
            total_deposits=Decimal(data.get("total_deposits", 0)),
            total_withdrawals=Decimal(data.get("total_withdrawals", 0)),
            event_count=data.get("event_count", 0),
        )
    
    def __repr__(self) -> str:
        return (
            f"Checkpoint(balance={self.balance}, "
            f"last_event_id={self.last_event_id}, "
            f"event_count={self.event_count})"
        )


class CheckpointManager:
    """
    Manages checkpoint creation, storage, and loading.
    Ensures checkpoints are correct and consistent.
    """
    
    def __init__(self, storage_backend: Optional[Dict] = None):
        """
        Initialize checkpoint manager.
        
        Args:
            storage_backend: Dict-based storage (for testing). In production, use database.
        """
        self.storage = storage_backend or {}
        self.lock = {}  # Simple in-memory locks for thread safety
    
    def create_checkpoint(
        self,
        balance: Decimal,
        last_event_id: int,
        node_id: str,
        account_id: int,
        total_deposits: Decimal = Decimal(0),
        total_withdrawals: Decimal = Decimal(0),
        event_count: int = 0,
    ) -> Checkpoint:
        """
        Create a new checkpoint.
        
        Args:
            balance: Current computed balance
            last_event_id: Last processed event ID
            node_id: ID of the node creating checkpoint
            account_id: Account ID
            total_deposits: Total deposits accumulated
            total_withdrawals: Total withdrawals accumulated
            event_count: Number of events processed
            
        Returns:
            Checkpoint object
        """
        checkpoint = Checkpoint(
            balance=balance,
            last_event_id=last_event_id,
            node_id=node_id,
            account_id=account_id,
            total_deposits=total_deposits,
            total_withdrawals=total_withdrawals,
            event_count=event_count,
        )
        logger.debug(
            f"Created checkpoint: node={node_id}, account={account_id}, "
            f"balance={balance}, last_event_id={last_event_id}"
        )
        return checkpoint
    
    def save_checkpoint(self, checkpoint: Checkpoint, storage_key: str) -> bool:
        """
        Save checkpoint to storage.
        
        Args:
            checkpoint: Checkpoint to save
            storage_key: Key for storage (e.g., "account_123_checkpoint")
            
        Returns:
            True if saved successfully
        """
        try:
            self.storage[storage_key] = checkpoint.to_dict()
            logger.info(
                f"Checkpoint saved: {storage_key} -> "
                f"balance={checkpoint.balance}, last_event_id={checkpoint.last_event_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save checkpoint {storage_key}: {e}")
            return False
    
    def load_checkpoint(self, storage_key: str) -> Optional[Checkpoint]:
        """
        Load checkpoint from storage.
        
        Args:
            storage_key: Key for storage
            
        Returns:
            Checkpoint if found, None otherwise
        """
        try:
            data = self.storage.get(storage_key)
            if data is None:
                return None
            checkpoint = Checkpoint.from_dict(data)
            logger.debug(f"Checkpoint loaded: {storage_key} -> {checkpoint}")
            return checkpoint
        except Exception as e:
            logger.error(f"Failed to load checkpoint {storage_key}: {e}")
            return None
    
    def get_or_create_checkpoint(
        self,
        storage_key: str,
        node_id: str,
        account_id: int,
        initial_balance: Decimal = Decimal(0),
    ) -> Checkpoint:
        """
        Get existing checkpoint or create a new one.
        
        Args:
            storage_key: Storage key
            node_id: Node ID
            account_id: Account ID
            initial_balance: Initial balance if creating new checkpoint
            
        Returns:
            Checkpoint object
        """
        checkpoint = self.load_checkpoint(storage_key)
        if checkpoint is None:
            checkpoint = self.create_checkpoint(
                balance=initial_balance,
                last_event_id=0,
                node_id=node_id,
                account_id=account_id,
            )
            self.save_checkpoint(checkpoint, storage_key)
        return checkpoint
    
    def verify_checkpoint(self, checkpoint: Checkpoint, computed_balance: Decimal) -> bool:
        """
        Verify checkpoint correctness by comparing with independently computed balance.
        
        Args:
            checkpoint: Checkpoint to verify
            computed_balance: Balance computed from events
            
        Returns:
            True if checkpoint matches computed balance
        """
        if checkpoint.balance != computed_balance:
            logger.warning(
                f"Checkpoint verification failed: "
                f"checkpoint_balance={checkpoint.balance}, "
                f"computed_balance={computed_balance}"
            )
            return False
        logger.debug(f"Checkpoint verification passed: {checkpoint}")
        return True
