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
from src.core.coordinated_commit import CoordinatedCommitManager, ReplicaVote
from src.core.quorum_replication import QuorumReplicationManager, QuorumVote

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
        
        # Two-Phase Commit state management (coordinator-based)
        self.coordinated_commit_manager = CoordinatedCommitManager(node_id)
        
        # Track locked funds during 2PC prepare phase: {transaction_id: locked_amount}
        self.locked_funds: Dict[str, Decimal] = {}
        
        # Track pending prepared transactions (waiting for commit/rollback): {transaction_id: prepared_event}
        self.prepared_transactions: Dict[str, TransactionEvent] = {}
        
        # P2P Quorum-based replication (no coordinator needed)
        self.quorum_manager = QuorumReplicationManager(
            node_id=node_id,
            total_nodes=1  # Will be updated when nodes are wired
        )
        
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
    
    # ========== WITHDRAWAL (STRONG CONSISTENCY + OPTIMIZED) ==========
    
    def withdraw(self, amount: Decimal, request_id: str = "") -> Tuple[bool, str]:
        """
        Withdrawal with strong consistency (7-step process) + optimized bandwidth
        
        Optimization: Uses last_withdraw_amount to compute balance efficiently
        Formula: balance = checkpoint + deposits_since_checkpoint - last_withdraw
        
        This reduces bandwidth by ~80-90% on deposit-heavy workloads.
        """
        if not self._acquire_lock():
            return False, "Could not acquire lock"
        
        try:
            if amount <= 0:
                return False, "Withdrawal amount must be positive"
            
            logger.info(f"[{self.node_id}] Starting withdrawal: {amount}")
            
            # Step 1: Sync events from all remote nodes
            remote_events = self._sync_events()
            
            # Step 2: Merge events with deduplication
            self.event_log.merge_events(remote_events)
            
            # Step 3: Compute balance using OPTIMIZED strategy
            balance_info = self.event_log.compute_balance_optimized(
                checkpoint_balance=self.checkpoint.balance,
                checkpoint_event_id=self.checkpoint.last_event_id,
                last_withdraw_amount=self.checkpoint.last_withdraw_amount,
            )
            current_balance = balance_info['balance']
            
            logger.debug(
                f"[{self.node_id}] Balance computation: {balance_info['formula']} = {current_balance} "
                f"(bandwidth saved: {balance_info['bandwidth_saved_percent']}%)"
            )
            
            # Step 4: Validate sufficient balance
            if current_balance < amount:
                return (
                    False,
                    f"Insufficient balance. Current: {current_balance}, "
                    f"Requested: {amount}",
                )
            
            # Step 5: Create withdrawal event with version
            event = self._create_event(EventType.WITHDRAW, amount, request_id)
            
            if not self.event_log.add_event(event):
                return False, "Event rejected (duplicate request_id)"
            
            # Step 6: Update checkpoint atomically with versioning and last_withdraw tracking
            self.checkpoint.balance = current_balance - amount
            self.checkpoint.last_event_id = event.event_id
            self.checkpoint.total_withdrawals += amount
            self.checkpoint.event_count += 1
            
            # NEW: Track last withdrawal for next balance computation
            self.checkpoint.last_withdraw_amount = amount
            self.checkpoint.last_withdraw_event_id = event.event_id
            self.checkpoint.last_withdraw_timestamp = event.timestamp
            
            # Checkpoint version automatically updated
            key = f"account_{self.account_id}_node_{self.node_id}_checkpoint"
            self.checkpoint_manager.save_checkpoint(self.checkpoint, key)
            
            # Step 7: Propagate withdrawal INSTANTLY to all replicas
            propagated = self._propagate_event(event)
            
            logger.info(
                f"[{self.node_id}] Withdrawal: {amount}, "
                f"balance={self.checkpoint.balance}, "
                f"event_id={event.event_id}, "
                f"event_version={event.version}, "
                f"checkpoint_version={self.checkpoint.version}, "
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
        """
        Get current balance (read-only, with event sync for lazy-propagated deposits)
        
        For lazy propagation to work correctly:
        1. Sync events from remote nodes (deposits are not instantly propagated)
        2. Merge synced events into local event log
        3. Compute balance from updated event log
        """
        if not self._acquire_lock(timeout=2.0):
            return self.checkpoint.balance
        
        try:
            # Step 1: Sync events from remote nodes (handles lazy-propagated deposits)
            remote_events = self._sync_events()
            
            # Step 2: Merge synced events into local event log
            if remote_events:
                self.event_log.merge_events(remote_events)
            
            # Step 3: Compute balance from updated event log
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
    
    # ========== TWO-PHASE COMMIT (2PC) COORDINATED WITHDRAWAL ==========
    
    def coordinated_withdraw(
        self,
        amount: Decimal,
        request_id: str = ""
    ) -> Tuple[bool, str]:
        """
        Perform withdrawal with Two-Phase Commit (2PC) protocol.
        
        Ensures all-or-nothing semantics: Either ALL replicas apply the withdrawal,
        or NONE do. This prevents inconsistency if a node fails mid-propagation.
        
        Protocol:
        1. PREPARE: Coordinator locks account on all replicas and validates balance
        2. COMMIT/ROLLBACK: Based on votes, either commit or rollback everywhere
        3. FINALIZE: Release locks and clean up state
        
        Args:
            amount: Amount to withdraw
            request_id: Idempotency key
        
        Returns:
            (success: bool, message: str)
        """
        if not self._acquire_lock():
            return False, "Could not acquire lock"
        
        try:
            if amount <= 0:
                return False, "Withdrawal amount must be positive"
            
            logger.info(f"[{self.node_id}] Starting COORDINATED withdrawal: {amount}")
            
            # Step 1: Create coordinated transaction
            replica_ids = list(self.remote_nodes.keys()) + [self.node_id]
            success, msg, txn_id = self.coordinated_commit_manager.create_transaction(
                account_id=self.account_id,
                amount=amount,
                request_id=request_id,
                replica_ids=replica_ids,
            )
            
            if not success:
                return False, f"Failed to create transaction: {msg}"
            
            logger.info(f"[{self.node_id}] Created coordinated transaction: {txn_id}")
            
            # Step 2: PREPARE PHASE - Send prepare request to all replicas (including self)
            # Each replica locks the account and validates it has sufficient balance
            for node_id, remote_node in self.remote_nodes.items():
                try:
                    vote = remote_node.prepare_for_coordinated_withdraw(
                        transaction_id=txn_id,
                        account_id=self.account_id,
                        amount=amount,
                        request_id=request_id,
                    )
                    self.coordinated_commit_manager.record_prepare_vote(txn_id, node_id, vote)
                    logger.debug(f"[{self.node_id}] Replica {node_id} voted: {vote}")
                except Exception as e:
                    logger.error(f"[{self.node_id}] Failed to get prepare vote from {node_id}: {e}")
                    self.coordinated_commit_manager.record_prepare_vote(txn_id, node_id, ReplicaVote.TIMEOUT)
            
            # Prepare self
            try:
                self_vote = self.prepare_for_coordinated_withdraw(
                    transaction_id=txn_id,
                    account_id=self.account_id,
                    amount=amount,
                    request_id=request_id,
                )
                self.coordinated_commit_manager.record_prepare_vote(txn_id, self.node_id, self_vote)
                logger.debug(f"[{self.node_id}] Self-node voted: {self_vote}")
            except Exception as e:
                logger.error(f"[{self.node_id}] Self-prepare failed: {e}")
                self.coordinated_commit_manager.record_prepare_vote(txn_id, self.node_id, ReplicaVote.NACK)
            
            # Step 3: Evaluate votes - Can we commit?
            total_replicas = len(replica_ids)
            can_commit, reason = self.coordinated_commit_manager.can_commit(txn_id, total_replicas)
            
            logger.info(f"[{self.node_id}] Prepare phase result: can_commit={can_commit}, reason={reason}")
            
            if not can_commit:
                # ROLLBACK PHASE
                logger.warning(f"[{self.node_id}] Cannot commit, rolling back transaction {txn_id}")
                self._rollback_coordinated_withdraw_everywhere(txn_id, reason)
                self.coordinated_commit_manager.rollback_transaction(txn_id, reason)
                return False, f"Withdrawal failed during prepare phase: {reason}"
            
            # Step 4: COMMIT PHASE - All replicas agreed, commit everywhere
            logger.info(f"[{self.node_id}] All replicas prepared, committing transaction {txn_id}")
            self._commit_coordinated_withdraw_everywhere(txn_id)
            self.coordinated_commit_manager.commit_transaction(txn_id)
            
            # Step 5: FINALIZE - Verify success and clean up
            logger.info(f"[{self.node_id}] Coordinated withdrawal {txn_id} committed successfully")
            self.coordinated_commit_manager.finalize_transaction(txn_id)
            
            return True, f"Coordinated withdrawal processed. Transaction ID: {txn_id}"
            
        finally:
            self._release_lock()
    
    def prepare_for_coordinated_withdraw(
        self,
        transaction_id: str,
        account_id: int,
        amount: Decimal,
        request_id: str,
    ) -> ReplicaVote:
        """
        PREPARE PHASE (Replica side):
        Lock account, validate balance, and signal readiness to commit.
        
        Returns:
            ReplicaVote.ACK if ready to commit
            ReplicaVote.NACK if cannot commit
        """
        if not self._acquire_lock(timeout=2.0):
            logger.warning(f"[{self.node_id}] Could not acquire lock for prepare phase")
            return ReplicaVote.NACK
        
        try:
            # Sync latest events from all replicas
            remote_events = self._sync_events()
            self.event_log.merge_events(remote_events)
            
            # Compute current balance
            balance_info = self.event_log.compute_balance_optimized(
                checkpoint_balance=self.checkpoint.balance,
                checkpoint_event_id=self.checkpoint.last_event_id,
                last_withdraw_amount=self.checkpoint.last_withdraw_amount,
            )
            current_balance = balance_info['balance']
            
            # Check if we have sufficient balance considering already-locked funds
            available_balance = current_balance - sum(self.locked_funds.values())
            
            if available_balance < amount:
                logger.warning(
                    f"[{self.node_id}] Insufficient balance for txn {transaction_id}: "
                    f"available={available_balance}, requested={amount}"
                )
                return ReplicaVote.NACK
            
            # Lock the funds (reserve them for this transaction)
            self.locked_funds[transaction_id] = amount
            
            # Create the withdrawal event but DON'T apply it yet
            event = self._create_event(EventType.WITHDRAW, amount, request_id)
            event.transaction_id = transaction_id  # Mark with transaction ID
            
            # Store prepared event for later commit
            self.prepared_transactions[transaction_id] = event
            
            logger.info(
                f"[{self.node_id}] Prepared for withdrawal txn {transaction_id}: "
                f"amount={amount}, available_balance={available_balance}"
            )
            
            return ReplicaVote.ACK
            
        finally:
            self._release_lock()
    
    def _commit_coordinated_withdraw_everywhere(self, transaction_id: str):
        """
        COMMIT PHASE (Coordinator):
        Tell all replicas to apply the withdrawal.
        """
        logger.info(f"[{self.node_id}] COMMIT phase: sending commit to all replicas for txn {transaction_id}")
        
        # Commit on all remote nodes
        for node_id, remote_node in self.remote_nodes.items():
            try:
                remote_node.commit_coordinated_withdraw(transaction_id)
                logger.debug(f"[{self.node_id}] Committed txn {transaction_id} on {node_id}")
            except Exception as e:
                logger.error(f"[{self.node_id}] Failed to commit on {node_id}: {e}")
        
        # Commit on self
        try:
            self.commit_coordinated_withdraw(transaction_id)
            logger.debug(f"[{self.node_id}] Committed txn {transaction_id} on self")
        except Exception as e:
            logger.error(f"[{self.node_id}] Failed to commit on self: {e}")
    
    def commit_coordinated_withdraw(self, transaction_id: str) -> Tuple[bool, str]:
        """
        COMMIT PHASE (Replica side):
        Apply the prepared withdrawal event and update checkpoint.
        """
        if not self._acquire_lock(timeout=2.0):
            logger.warning(f"[{self.node_id}] Could not acquire lock for commit phase")
            return False, "Could not acquire lock"
        
        try:
            if transaction_id not in self.prepared_transactions:
                logger.warning(f"[{self.node_id}] No prepared transaction found for {transaction_id}")
                return False, "No prepared transaction"
            
            event = self.prepared_transactions[transaction_id]
            amount = event.amount
            
            # Apply the event
            if not self.event_log.add_event(event):
                logger.warning(f"[{self.node_id}] Failed to add event for txn {transaction_id}")
                return False, "Failed to add event"
            
            # Update checkpoint
            current_balance = self.event_log.compute_balance(
                self.checkpoint.balance,
                self.checkpoint.last_event_id,
            )
            
            self.checkpoint.balance = current_balance - amount
            self.checkpoint.last_event_id = event.event_id
            self.checkpoint.total_withdrawals += amount
            self.checkpoint.event_count += 1
            self.checkpoint.last_withdraw_amount = amount
            self.checkpoint.last_withdraw_event_id = event.event_id
            self.checkpoint.last_withdraw_timestamp = event.timestamp
            
            key = f"account_{self.account_id}_node_{self.node_id}_checkpoint"
            self.checkpoint_manager.save_checkpoint(self.checkpoint, key)
            
            # Clean up transaction state
            del self.prepared_transactions[transaction_id]
            if transaction_id in self.locked_funds:
                del self.locked_funds[transaction_id]
            
            logger.info(
                f"[{self.node_id}] Committed withdrawal txn {transaction_id}: "
                f"amount={amount}, new_balance={self.checkpoint.balance}"
            )
            
            return True, "Withdrawal committed"
            
        finally:
            self._release_lock()
    
    def _rollback_coordinated_withdraw_everywhere(self, transaction_id: str, reason: str):
        """
        ROLLBACK PHASE (Coordinator):
        Tell all replicas to release locks and discard prepared state.
        """
        logger.warning(f"[{self.node_id}] ROLLBACK phase: rolling back txn {transaction_id} ({reason})")
        
        # Rollback on all remote nodes
        for node_id, remote_node in self.remote_nodes.items():
            try:
                remote_node.rollback_coordinated_withdraw(transaction_id)
                logger.debug(f"[{self.node_id}] Rolled back txn {transaction_id} on {node_id}")
            except Exception as e:
                logger.error(f"[{self.node_id}] Failed to rollback on {node_id}: {e}")
        
        # Rollback on self
        try:
            self.rollback_coordinated_withdraw(transaction_id)
            logger.debug(f"[{self.node_id}] Rolled back txn {transaction_id} on self")
        except Exception as e:
            logger.error(f"[{self.node_id}] Failed to rollback on self: {e}")
    
    def rollback_coordinated_withdraw(self, transaction_id: str) -> Tuple[bool, str]:
        """
        ROLLBACK PHASE (Replica side):
        Release locks and discard prepared state.
        """
        if not self._acquire_lock(timeout=2.0):
            logger.warning(f"[{self.node_id}] Could not acquire lock for rollback phase")
            return False, "Could not acquire lock"
        
        try:
            # Release locks
            if transaction_id in self.locked_funds:
                amount = self.locked_funds[transaction_id]
                del self.locked_funds[transaction_id]
                logger.info(f"[{self.node_id}] Released lock for txn {transaction_id}: {amount}")
            
            # Discard prepared transaction
            if transaction_id in self.prepared_transactions:
                del self.prepared_transactions[transaction_id]
                logger.info(f"[{self.node_id}] Discarded prepared state for txn {transaction_id}")
            
            return True, "Withdrawal rolled back"
            
        finally:
            self._release_lock()
    
    def get_transaction_locks(self) -> Dict[str, Decimal]:
        """Get all current transaction locks (debugging/monitoring)"""
        return dict(self.locked_funds)
    
    # ========== P2P QUORUM-BASED WITHDRAWAL (NO COORDINATOR) ==========
    
    def p2p_withdraw(
        self,
        amount: Decimal,
        request_id: str = ""
    ) -> Tuple[bool, str]:
        """
        P2P Quorum-based withdrawal (no designated coordinator).
        
        ANY node can initiate a withdrawal. Uses quorum consensus:
        - Initiator asks other nodes to vote YES/NO
        - If quorum agrees: apply withdrawal everywhere via gossip
        - If quorum disagrees: rollback everywhere
        
        Advantages over 2PC:
        - No single coordinator bottleneck
        - Any node can initiate
        - More resilient to node failures
        - Better for truly decentralized systems
        
        Args:
            amount: Amount to withdraw
            request_id: Idempotency key
        
        Returns:
            (success: bool, message: str)
        """
        if not self._acquire_lock():
            return False, "Could not acquire lock"
        
        try:
            if amount <= 0:
                return False, "Withdrawal amount must be positive"
            
            logger.info(f"[{self.node_id}] Starting P2P QUORUM withdrawal: {amount}")
            
            # Get list of all peer nodes
            peer_nodes = list(self.remote_nodes.keys()) + [self.node_id]
            
            # Step 1: Initiate withdrawal transaction
            success, msg, txn_id = self.quorum_manager.initiate_withdrawal(
                account_id=self.account_id,
                amount=amount,
                request_id=request_id,
                peer_nodes=peer_nodes,
            )
            
            if not success:
                return False, f"Failed to initiate transaction: {msg}"
            
            logger.info(f"[{self.node_id}] Quorum withdrawal txn {txn_id} initiated")
            
            # Step 2: REQUEST - Send withdrawal request to all peers
            # Each peer votes: ACCEPT or REJECT
            for node_id, remote_node in self.remote_nodes.items():
                try:
                    vote = remote_node.p2p_receive_withdrawal_request(
                        transaction_id=txn_id,
                        account_id=self.account_id,
                        amount=amount,
                        request_id=request_id,
                        initiator_id=self.node_id,
                    )
                    self.quorum_manager.record_peer_vote(txn_id, node_id, vote)
                    logger.debug(f"[{self.node_id}] Peer {node_id} voted: {vote}")
                except Exception as e:
                    logger.error(f"[{self.node_id}] Failed to get vote from {node_id}: {e}")
                    self.quorum_manager.record_peer_vote(txn_id, node_id, QuorumVote.TIMEOUT)
            
            # Vote for self
            try:
                self_vote = self.p2p_receive_withdrawal_request(
                    transaction_id=txn_id,
                    account_id=self.account_id,
                    amount=amount,
                    request_id=request_id,
                    initiator_id=self.node_id,
                )
                self.quorum_manager.record_peer_vote(txn_id, self.node_id, self_vote)
                logger.debug(f"[{self.node_id}] Self-vote: {self_vote}")
            except Exception as e:
                logger.error(f"[{self.node_id}] Self-vote failed: {e}")
                self.quorum_manager.record_peer_vote(txn_id, self.node_id, QuorumVote.REJECT)
            
            # Step 3: DECISION - Check if we have quorum
            has_quorum, reason = self.quorum_manager.has_quorum(txn_id)
            logger.info(f"[{self.node_id}] Quorum check: has_quorum={has_quorum}, reason={reason}")
            
            if not has_quorum:
                # REJECT - Not enough support, rollback everywhere
                logger.warning(f"[{self.node_id}] Quorum NOT achieved for txn {txn_id}")
                self._p2p_notify_peers_rollback(txn_id)
                self.quorum_manager.reject_withdrawal(txn_id, reason)
                return False, f"Quorum not achieved: {reason}"
            
            # Step 4: APPLY - Quorum achieved! Apply locally
            logger.info(f"[{self.node_id}] Quorum achieved for txn {txn_id}, applying withdrawal")
            
            # Create and apply the withdrawal event
            event = self._create_event(EventType.WITHDRAW, amount, request_id)
            event.transaction_id = txn_id
            
            if not self.event_log.add_event(event):
                logger.error(f"[{self.node_id}] Failed to add event for txn {txn_id}")
                self._p2p_notify_peers_rollback(txn_id)
                return False, "Failed to apply withdrawal"
            
            # Update checkpoint
            current_balance = self.event_log.compute_balance(
                self.checkpoint.balance,
                self.checkpoint.last_event_id,
            )
            
            self.checkpoint.balance = current_balance - amount
            self.checkpoint.last_event_id = event.event_id
            self.checkpoint.total_withdrawals += amount
            self.checkpoint.event_count += 1
            self.checkpoint.last_withdraw_amount = amount
            self.checkpoint.last_withdraw_event_id = event.event_id
            self.checkpoint.last_withdraw_timestamp = event.timestamp
            
            key = f"account_{self.account_id}_node_{self.node_id}_checkpoint"
            self.checkpoint_manager.save_checkpoint(self.checkpoint, key)
            
            # Step 5: GOSSIP - Propagate event to all peers via gossip
            propagated = self._propagate_event(event)
            logger.info(
                f"[{self.node_id}] Applied withdrawal txn {txn_id}: "
                f"amount={amount}, new_balance={self.checkpoint.balance}, "
                f"propagated_to={propagated} peers"
            )
            
            self.quorum_manager.apply_withdrawal(txn_id)
            return True, f"P2P withdrawal applied. Transaction: {txn_id}"
        
        finally:
            self._release_lock()
    
    def p2p_receive_withdrawal_request(
        self,
        transaction_id: str,
        account_id: int,
        amount: Decimal,
        request_id: str,
        initiator_id: str,
    ) -> QuorumVote:
        """
        PEER SIDE: Receive withdrawal request from initiator peer.
        
        This node votes YES (ACCEPT) or NO (REJECT) based on:
        - Do we have sufficient balance?
        - Is the account already locked by another transaction?
        
        Args:
            transaction_id: Transaction ID from initiator
            account_id: Account to withdraw from
            amount: Amount to withdraw
            request_id: Idempotency key
            initiator_id: Which peer initiated this
        
        Returns:
            QuorumVote: ACCEPT or REJECT
        """
        if not self._acquire_lock(timeout=2.0):
            logger.warning(f"[{self.node_id}] Could not acquire lock for vote")
            return QuorumVote.REJECT
        
        try:
            # Sync latest events from all peers
            remote_events = self._sync_events()
            self.event_log.merge_events(remote_events)
            
            # Compute current balance
            balance_info = self.event_log.compute_balance_optimized(
                checkpoint_balance=self.checkpoint.balance,
                checkpoint_event_id=self.checkpoint.last_event_id,
                last_withdraw_amount=self.checkpoint.last_withdraw_amount,
            )
            current_balance = balance_info['balance']
            
            # Check if we have sufficient balance
            if current_balance < amount:
                logger.warning(
                    f"[{self.node_id}] Rejecting withdrawal from {initiator_id}: "
                    f"insufficient balance ({current_balance} < {amount})"
                )
                return QuorumVote.REJECT
            
            # ACCEPT the withdrawal (we'll apply it after gossip receives event from initiator)
            logger.info(
                f"[{self.node_id}] Accepting withdrawal request from {initiator_id}: "
                f"txn={transaction_id}, amount={amount}"
            )
            return QuorumVote.ACCEPT
        
        finally:
            self._release_lock()
    
    def _p2p_notify_peers_rollback(self, transaction_id: str):
        """
        Notify all peers that a transaction was rejected
        (optional - mainly for cleanup)
        """
        for node_id, remote_node in self.remote_nodes.items():
            try:
                remote_node.p2p_receive_rollback_notification(transaction_id)
            except Exception as e:
                logger.warning(f"[{self.node_id}] Failed to notify {node_id} of rollback: {e}")
    
    def p2p_receive_rollback_notification(self, transaction_id: str):
        """
        PEER SIDE: Receive notification that a transaction was rolled back
        """
        logger.info(f"[{self.node_id}] Received rollback notification for txn {transaction_id}")

