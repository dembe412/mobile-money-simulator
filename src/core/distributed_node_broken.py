"""
Distributed Node Implementation
Implements the core logic for deposits, withdrawals, and event synchronization
using checkpoint + versioning approach
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import logging
import threading
from enum import Enum
import time
import uuid

from src.core.checkpoint import Checkpoint, CheckpointManager
from src.core.event_log import EventLog, TransactionEvent, EventType

logger = logging.getLogger(__name__)


class WithdrawalStatus(str, Enum):
    """Status of withdrawal operations"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REPLICATED = "replicated"


class EventIDGenerator:
    """
    Generates globally unique event IDs using timestamp + node_id + counter.
    Ensures no collisions across distributed nodes.
    """
    
    def __init__(self, node_id: str):
        """Initialize ID generator for a node"""
        self.node_id = node_id
        self.counter = 0
        self.last_timestamp_ms = 0
        self.lock = threading.Lock()
    
    def next_id(self) -> int:
        """
        Generate next globally unique event ID.
        
        Format: (timestamp_ms << 16) | (node_hash << 8) | counter
        This ensures:
        - Monotonically increasing within node
        - Unique across nodes
        - Sortable by timestamp
        
        Returns:
            Globally unique event ID
        """
        with self.lock:
            current_time_ms = int(time.time() * 1000)
            
            # If same millisecond, increment counter
            if current_time_ms == self.last_timestamp_ms:
                self.counter += 1
            else:
                self.counter = 0
                self.last_timestamp_ms = current_time_ms
            
            # Create unique ID: timestamp (high bits) + node_hash + counter
            node_hash = hash(self.node_id) & 0xFF  # 8 bits
            event_id = (current_time_ms << 16) | (node_hash << 8) | (self.counter & 0xFF)
            
            return event_id


class DistributedNode:
    """
    A single node in the distributed mobile money system.
    
    Implements:
    - Lazy propagation for deposits
    - Strong consistency for withdrawals
    - Checkpoint + versioning to minimize bandwidth
    - Event-based state management
    
    Key responsibilities:
    1. Maintain local event log
    2. Maintain checkpoint of processed state
    3. Handle deposits (accept locally, store as events)
    4. Handle withdrawals (sync, compute, validate, propagate)
    5. Sync events with remote nodes
    """
    
    def __init__(
        self,
        node_id: str,
        account_id: int,
        initial_balance: Decimal = Decimal(0),
        min_replicas: int = 1,
    ):
        """
        Initialize a distributed node.
        
        Args:
            node_id: Unique identifier for this node
            account_id: Account ID managed by this node
            initial_balance: Initial balance
            min_replicas: Minimum number of nodes for quorum (for withdrawal approval)
        """
        self.node_id = node_id
        self.account_id = account_id
        self.min_replicas = min_replicas
        
        # Core components
        self.event_log = EventLog()
        self.checkpoint_manager = CheckpointManager()  # Each node has independent storage
        self.event_id_generator = EventIDGenerator(node_id)
        
        # Initialize checkpoint with unique key per node
        checkpoint_key = f"account_{account_id}_node_{node_id}_checkpoint"
        self.checkpoint = self.checkpoint_manager.get_or_create_checkpoint(
            checkpoint_key, node_id, account_id, initial_balance
        )
        
        # Synchronization state
        self.remote_nodes: Dict[str, "DistributedNode"] = {}  # For simulation
        self.lock = threading.RLock()
        
        logger.info(
            f"Node initialized: {node_id}, account={account_id}, "
            f"balance={initial_balance}, min_replicas={min_replicas}"
        )
    
    def _acquire_lock(self, timeout: float = 5.0) -> bool:
        """Acquire operation lock"""
        return self.lock.acquire(timeout=timeout)
    
    def _release_lock(self):
        """Release operation lock"""
        self.lock.release()
    
    # ============ DEPOSIT OPERATIONS (LAZY PROPAGATION) ============
    
    def deposit(self, amount: Decimal, request_id: str = "") -> Tuple[bool, str]:
        """
        Process a deposit (lazy propagation).
        
        Process:
        1. Create deposit event
        2. Add to local event log
        3. Update checkpoint
        4. Return success (no propagation)
        
        Args:
            amount: Amount to deposit
            request_id: Optional request ID for idempotency
            
        Returns:
            (success: bool, message: str)
        """
        if not self._acquire_lock():
            return False, "Could not acquire lock"
        
        try:
            # Validate amount
            if amount <= 0:
                return False, "Deposit amount must be positive"
            
            # Create deposit event
            event = self._create_event(
                event_type=EventType.DEPOSIT,
                amount=amount,
                request_id=request_id,
            )
            
            # Add to log
            if not self.event_log.add_event(event):
                return False, "Event rejected (duplicate request_id)"
            
            # Update checkpoint incrementally
            self.checkpoint.balance += amount
            self.checkpoint.last_event_id = event.event_id
            self.checkpoint.total_deposits += amount
            self.checkpoint.event_count += 1
            
            # Persist checkpoint with unique key
            checkpoint_key = f"account_{self.account_id}_node_{self.node_id}_checkpoint"
            self.checkpoint_manager.save_checkpoint(self.checkpoint, checkpoint_key)
            
            logger.info(
                f"[{self.node_id}] Deposit successful: "
                f"amount={amount}, new_balance={self.checkpoint.balance}, "
                f"event_id={event.event_id}"
            )
            
            return True, f"Deposit processed. Event ID: {event.event_id}"
        
        finally:
            self._release_lock()
    
    # ============ WITHDRAWAL OPERATIONS (STRONG CONSISTENCY) ============
    
    def withdraw(self, amount: Decimal, request_id: str = "") -> Tuple[bool, str]:
        """
        Process a withdrawal (strong consistency).
        
        Strict 7-step process:
        1. Sync events from all nodes
        2. Merge events into local log
        3. Compute current balance
        4. Validate withdrawal amount
        5. Create withdrawal event
        6. Update checkpoint
        7. Propagate to all nodes
        
        Args:
            amount: Amount to withdraw
            request_id: Optional request ID for idempotency
            
        Returns:
            (success: bool, message: str)
        """
        if not self._acquire_lock():
            return False, "Could not acquire lock"
        
        try:
            # Validate amount
            if amount <= 0:
                return False, "Withdrawal amount must be positive"
            
            logger.info(
                f"[{self.node_id}] Starting withdrawal: amount={amount}"
            )
            
            # ===== STEP 1: SYNC EVENTS =====
            logger.debug(f"[{self.node_id}] Step 1: Syncing events...")
            remote_events = self._sync_events()
            
            # ===== STEP 2: MERGE EVENTS =====
            logger.debug(f"[{self.node_id}] Step 2: Merging {len(remote_events)} remote events...")
            self.event_log.merge_events(remote_events)
            
            # ===== STEP 3: COMPUTE BALANCE =====
            logger.debug(f"[{self.node_id}] Step 3: Computing current balance...")
            current_balance = self._compute_current_balance()
            
            logger.debug(
                f"[{self.node_id}] Balance computation: "
                f"checkpoint_balance={self.checkpoint.balance}, "
                f"checkpoint_event_id={self.checkpoint.last_event_id}, "
                f"current_balance={current_balance}"
            )
            
            # ===== STEP 4: VALIDATE WITHDRAWAL =====
            logger.debug(f"[{self.node_id}] Step 4: Validating withdrawal...")
            if current_balance < amount:
                return (
                checkpoint_key = f"account_{self.account_id}_node_{self.node_id}_checkpoint"
                self.checkpoint_manager.save_checkpoint(self.checkpoint, checkpoint_key)
                    f"Requested: {amount}",
                )
            
            # ===== STEP 5: CREATE WITHDRAWAL EVENT =====
            logger.debug(f"[{self.node_id}] Step 5: Creating withdrawal event...")
            event = self._create_event(
                event_type=EventType.WITHDRAW,
                amount=amount,
                request_id=request_id,
            )
            
            if not self.event_log.add_event(event):
                return False, "Event rejected (duplicate request_id)"
            
            # ===== STEP 6: UPDATE CHECKPOINT =====
            logger.debug(f"[{self.node_id}] Step 6: Updating checkpoint...")
            self.checkpoint.balance = current_balance - amount
            self.checkpoint.last_event_id = event.event_id
            self.checkpoint.total_withdrawals += amount
            self.checkpoint.event_count += 1
            
              checkpoint_key = f"account_{self.account_id}_node_{self.node_id}_checkpoint"
              self.checkpoint_manager.save_checkpoint(self.checkpoint, checkpoint_key)
            
            # ===== STEP 7: PROPAGATE WITHDRAWAL =====
            logger.debug(f"[{self.node_id}] Step 7: Propagating withdrawal...")
            propagated = self._propagate_event(event)
            
            logger.info(
                f"[{self.node_id}] Withdrawal successful: "
                f"amount={amount}, new_balance={self.checkpoint.balance}, "
                f"event_id={event.event_id}, propagated_to={propagated} nodes"
            )
            
            return True, f"Withdrawal processed. Event ID: {event.event_id}"
        
        finally:
            self._release_lock()
    
    # ============ EVENT CREATION ============
    
    def _create_event(
        self,
        event_type: EventType,
        amount: Decimal,
        request_id: str = "",
    ) -> TransactionEvent:
        """
        Create a new event with globally unique ID.
        
        Uses EventIDGenerator to ensure no collisions across nodes.
        
        Args:
            event_type: Type of event
            amount: Transaction amount
            request_id: Optional request ID
            
        Returns:
            TransactionEvent
        """
        event = TransactionEvent(
            event_id=self.event_id_generator.next_id(),
            type=event_type,
            amount=amount,
            account_id=self.account_id,
            node_id=self.node_id,
            request_id=request_id,
            timestamp=datetime.utcnow(),
        )
        return event
    
    # ============ SYNCHRONIZATION ============
    
    def _sync_events(self) -> List[TransactionEvent]:
        """
        Sync events from all remote nodes.
        
        Fetches only events after checkpoint (optimization).
        
        Returns:
            List of remote events to merge
        """
        all_remote_events = []
        
        for node_id, remote_node in self.remote_nodes.items():
            try:
                remote_events = remote_node.get_events_after(
                    self.checkpoint.last_event_id
                )
                
                logger.debug(
                    f"[{self.node_id}] Synced {len(remote_events)} events "
                    f"from {node_id} (after_id={self.checkpoint.last_event_id})"
                )
                
                all_remote_events.extend(remote_events)
            except Exception as e:
                logger.warning(
                    f"[{self.node_id}] Failed to sync from {node_id}: {e}"
                )
        
        # Deduplicate by event_id (in case multiple nodes have same event)
        seen_ids = {}
        for event in all_remote_events:
            if event.event_id not in seen_ids:
                seen_ids[event.event_id] = event
        
        unique_events = list(seen_ids.values())
        unique_events.sort(key=lambda e: e.event_id)
        
        return unique_events
    
    def get_events_after(self, after_event_id: int) -> List[TransactionEvent]:
        """
        Get all events after a certain event ID.
        
        Used by other nodes during sync.
        
        Args:
            after_event_id: Return events with event_id > this value
            
        Returns:
            List of events
        """
        return self.event_log.get_events_after(after_event_id)
    
    def _propagate_event(self, event: TransactionEvent) -> int:
        """
        Propagate event to all remote nodes.
        
        Used for withdrawals to ensure strong consistency.
        
        Args:
            event: Event to propagate
            
        Returns:
            Number of nodes that received the event
        """
        propagated_count = 0
        
        for node_id, remote_node in self.remote_nodes.items():
            try:
                success = remote_node.receive_event(event)
                if success:
                    propagated_count += 1
                    logger.debug(f"[{self.node_id}] Event {event.event_id} propagated to {node_id}")
            except Exception as e:
                logger.warning(
                    f"[{self.node_id}] Failed to propagate event {event.event_id} to {node_id}: {e}"
                )
        
        return propagated_count
    
    def receive_event(self, event: TransactionEvent) -> bool:
        """
        Receive an event from another node.
        
        Args:
            event: Event to receive
            
        Returns:
            True if event was added
        """
        if not self._acquire_lock(timeout=2.0):
            logger.warning(f"[{self.node_id}] Could not acquire lock to receive event")
            return False
        
        try:
            return self.event_log.add_event(event)
        finally:
            self._release_lock()
    
    # ============ BALANCE COMPUTATION ============
    
    def _compute_current_balance(self) -> Decimal:
        """
        Compute current balance from checkpoint + subsequent events.
        
        Formula:
            balance = checkpoint.balance + sum(events after checkpoint)
        
        This is O(n) where n is the number of events since checkpoint,
        not the total number of events.
        
        Returns:
            Current balance
        """
        return self.event_log.compute_balance(
            self.checkpoint.balance,
            self.checkpoint.last_event_id,
        )
    
    def get_balance(self) -> Decimal:
        """
        Get current balance (read-only).
        
        Returns:
            Current balance
        """
        if not self._acquire_lock(timeout=2.0):
            logger.warning(f"[{self.node_id}] Could not acquire lock to get balance")
            return self.checkpoint.balance
        
        try:
            return self._compute_current_balance()
        finally:
            self._release_lock()
    
    # ============ STATE INSPECTION ============
    
    def get_state(self) -> Dict:
        """
        Get complete node state for inspection.
        
        Returns:
            Dictionary with node state
        """
        if not self._acquire_lock(timeout=2.0):
            return {"error": "Could not acquire lock"}
        
        try:
            return {
                "node_id": self.node_id,
                "account_id": self.account_id,
                "balance": str(self.get_balance()),
                "checkpoint": self.checkpoint.to_dict(),
                "event_count": len(self.event_log),
                "max_event_id": self.event_log.max_event_id,
                "remote_nodes": list(self.remote_nodes.keys()),
            }
        finally:
            self._release_lock()
    
    def get_events(self) -> List[Dict]:
        """
        Get all events in log.
        
        Returns:
            List of event dictionaries
        """
        if not self._acquire_lock(timeout=2.0):
            return []
        
        try:
            return [e.to_dict() for e in self.event_log.get_all_events()]
        finally:
            self._release_lock()
    
    def __repr__(self) -> str:
        balance = self.get_balance()
        return (
            f"Node({self.node_id}, account={self.account_id}, "
            f"balance={balance}, events={len(self.event_log)})"
        )
