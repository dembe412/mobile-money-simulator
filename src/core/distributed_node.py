"""
Distributed Node Implementation - FIXED VERSION
Implements core logic for deposits, withdrawals, and event synchronization
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import logging
import threading
import time

from src.core.checkpoint import Checkpoint, CheckpointManager
from src.core.event_log import EventLog, TransactionEvent, EventType

logger = logging.getLogger(__name__)


class EventIDGenerator:
    """Generates globally unique event IDs across nodes"""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.counter = 0
        self.last_timestamp_ms = 0
        self.lock = threading.Lock()
    
    def next_id(self) -> int:
        """Generate next globally unique event ID"""
        with self.lock:
            current_time_ms = int(time.time() * 1000)
            if current_time_ms == self.last_timestamp_ms:
                self.counter += 1
            else:
                self.counter = 0
                self.last_timestamp_ms = current_time_ms
            
            node_hash = hash(self.node_id) & 0xFF
            event_id = (current_time_ms << 16) | (node_hash << 8) | (self.counter & 0xFF)
            return event_id


class DistributedNode:
    """Single node in distributed mobile money system"""
    
    def __init__(
        self,
        node_id: str,
        account_id: int,
        initial_balance: Decimal = Decimal(0),
        min_replicas: int = 1,
    ):
        self.node_id = node_id
        self.account_id = account_id
        self.min_replicas = min_replicas
        
        self.event_log = EventLog()
        self.checkpoint_manager = CheckpointManager()
        self.event_id_generator = EventIDGenerator(node_id)
        
        checkpoint_key = f"account_{account_id}_node_{node_id}_checkpoint"
        self.checkpoint = self.checkpoint_manager.get_or_create_checkpoint(
            checkpoint_key, node_id, account_id, initial_balance
        )
        
        self.remote_nodes: Dict[str, "DistributedNode"] = {}
        self.lock = threading.RLock()
        
        logger.info(
            f"Node initialized: {node_id}, account={account_id}, "
            f"balance={initial_balance}, min_replicas={min_replicas}"
        )
    
    def _acquire_lock(self, timeout: float = 5.0) -> bool:
        return self.lock.acquire(timeout=timeout)
    
    def _release_lock(self):
        self.lock.release()
    
    # ========== DEPOSIT (LAZY PROPAGATION) ==========
    
    def deposit(self, amount: Decimal, request_id: str = "") -> Tuple[bool, str]:
        """Deposit with lazy propagation"""
        if not self._acquire_lock():
            return False, "Could not acquire lock"
        
        try:
            if amount <= 0:
                return False, "Deposit amount must be positive"
            
            event = self._create_event(EventType.DEPOSIT, amount, request_id)
            
            if not self.event_log.add_event(event):
                return False, "Event rejected (duplicate request_id)"
            
            self.checkpoint.balance += amount
            self.checkpoint.last_event_id = event.event_id
            self.checkpoint.total_deposits += amount
            self.checkpoint.event_count += 1
            
            key = f"account_{self.account_id}_node_{self.node_id}_checkpoint"
            self.checkpoint_manager.save_checkpoint(self.checkpoint, key)
            
            logger.info(
                f"[{self.node_id}] Deposit: {amount}, "
                f"balance={self.checkpoint.balance}, event_id={event.event_id}"
            )
            
            return True, f"Deposit processed. Event ID: {event.event_id}"
        finally:
            self._release_lock()
    
    # ========== WITHDRAWAL (STRONG CONSISTENCY) ==========
    
    def withdraw(self, amount: Decimal, request_id: str = "") -> Tuple[bool, str]:
        """Withdrawal with strong consistency (7-step process)"""
        if not self._acquire_lock():
            return False, "Could not acquire lock"
        
        try:
            if amount <= 0:
                return False, "Withdrawal amount must be positive"
            
            logger.info(f"[{self.node_id}] Starting withdrawal: {amount}")
            
            # Step 1: Sync events
            remote_events = self._sync_events()
            
            # Step 2: Merge events
            self.event_log.merge_events(remote_events)
            
            # Step 3: Compute balance
            current_balance = self._compute_current_balance()
            
            # Step 4: Validate
            if current_balance < amount:
                return (
                    False,
                    f"Insufficient balance. Current: {current_balance}, "
                    f"Requested: {amount}",
                )
            
            # Step 5: Create event
            event = self._create_event(EventType.WITHDRAW, amount, request_id)
            
            if not self.event_log.add_event(event):
                return False, "Event rejected (duplicate request_id)"
            
            # Step 6: Update checkpoint
            self.checkpoint.balance = current_balance - amount
            self.checkpoint.last_event_id = event.event_id
            self.checkpoint.total_withdrawals += amount
            self.checkpoint.event_count += 1
            
            key = f"account_{self.account_id}_node_{self.node_id}_checkpoint"
            self.checkpoint_manager.save_checkpoint(self.checkpoint, key)
            
            # Step 7: Propagate
            propagated = self._propagate_event(event)
            
            logger.info(
                f"[{self.node_id}] Withdrawal: {amount}, "
                f"balance={self.checkpoint.balance}, event_id={event.event_id}, "
                f"propagated_to={propagated} nodes"
            )
            
            return True, f"Withdrawal processed. Event ID: {event.event_id}"
        finally:
            self._release_lock()
    
    # ========== EVENT CREATION ==========
    
    def _create_event(
        self,
        event_type: EventType,
        amount: Decimal,
        request_id: str = "",
    ) -> TransactionEvent:
        """Create event with globally unique ID"""
        return TransactionEvent(
            event_id=self.event_id_generator.next_id(),
            type=event_type,
            amount=amount,
            account_id=self.account_id,
            node_id=self.node_id,
            request_id=request_id,
            timestamp=datetime.utcnow(),
        )
    
    # ========== SYNCHRONIZATION ==========
    
    def _sync_events(self) -> List[TransactionEvent]:
        """Sync events from all remote nodes"""
        all_remote_events = []
        
        for node_id, remote_node in self.remote_nodes.items():
            try:
                remote_events = remote_node.get_events_after(
                    self.checkpoint.last_event_id
                )
                logger.debug(
                    f"[{self.node_id}] Synced {len(remote_events)} events from {node_id}"
                )
                all_remote_events.extend(remote_events)
            except Exception as e:
                logger.warning(f"[{self.node_id}] Failed to sync from {node_id}: {e}")
        
        # Deduplicate
        seen_ids = {}
        for event in all_remote_events:
            if event.event_id not in seen_ids:
                seen_ids[event.event_id] = event
        
        unique_events = list(seen_ids.values())
        unique_events.sort(key=lambda e: e.event_id)
        
        return unique_events
    
    def get_events_after(self, after_event_id: int) -> List[TransactionEvent]:
        """Get all events after ID (for other nodes to sync)"""
        return self.event_log.get_events_after(after_event_id)
    
    def _propagate_event(self, event: TransactionEvent) -> int:
        """Propagate event to all remote nodes"""
        propagated_count = 0
        
        for node_id, remote_node in self.remote_nodes.items():
            try:
                if remote_node.receive_event(event):
                    propagated_count += 1
                    logger.debug(f"[{self.node_id}] Event {event.event_id} propagated to {node_id}")
            except Exception as e:
                logger.warning(f"[{self.node_id}] Failed to propagate to {node_id}: {e}")
        
        return propagated_count
    
    def receive_event(self, event: TransactionEvent) -> bool:
        """Receive event from remote node"""
        if not self._acquire_lock(timeout=2.0):
            logger.warning(f"[{self.node_id}] Could not acquire lock to receive event")
            return False
        
        try:
            return self.event_log.add_event(event)
        finally:
            self._release_lock()
    
    # ========== BALANCE COMPUTATION ==========
    
    def _compute_current_balance(self) -> Decimal:
        """Compute balance from checkpoint + subsequent events"""
        return self.event_log.compute_balance(
            self.checkpoint.balance,
            self.checkpoint.last_event_id,
        )
    
    def get_balance(self) -> Decimal:
        """Get current balance (read-only)"""
        if not self._acquire_lock(timeout=2.0):
            return self.checkpoint.balance
        
        try:
            return self._compute_current_balance()
        finally:
            self._release_lock()
    
    # ========== STATE INSPECTION ==========
    
    def get_state(self) -> Dict:
        """Get complete node state"""
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
        """Get all events in log"""
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
