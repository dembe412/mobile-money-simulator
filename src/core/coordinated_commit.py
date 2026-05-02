"""
Two-Phase Commit (2PC) Protocol for Atomic Withdrawals
Ensures all or nothing semantics across distributed replicas
"""
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import logging
import uuid

logger = logging.getLogger(__name__)


class CommitPhase(str, Enum):
    """Phases of 2PC protocol"""
    PREPARE = "prepare"      # Ask replicas to prepare
    COMMIT = "commit"        # Tell replicas to commit
    ROLLBACK = "rollback"    # Tell replicas to rollback
    ABORT = "abort"          # Transaction aborted


class ReplicaVote(str, Enum):
    """Replica's vote in prepare phase"""
    ACK = "ack"              # Ready to commit
    NACK = "nack"            # Cannot commit
    TIMEOUT = "timeout"      # Did not respond


@dataclass
class LockRequest:
    """Lock request for account on a node"""
    transaction_id: str
    account_id: int
    amount: Decimal
    request_id: str
    timestamp: datetime


@dataclass
class CommitTransaction:
    """Represents a transaction being committed"""
    transaction_id: str  # Unique transaction identifier
    coordinator_id: str  # Node initiating the transaction
    account_id: int
    amount: Decimal
    request_id: str
    
    # Voting state
    votes: Dict[str, ReplicaVote] = None  # {replica_id: vote}
    prepare_acks: int = 0
    prepare_nacks: int = 0
    prepare_timeouts: int = 0
    
    # Status
    status: CommitPhase = CommitPhase.PREPARE
    created_at: datetime = None
    
    def __post_init__(self):
        if self.votes is None:
            self.votes = {}
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    def is_prepared_success(self, required_acks: int) -> bool:
        """Check if prepare phase succeeded"""
        return self.prepare_acks >= required_acks and self.prepare_nacks == 0
    
    def add_vote(self, replica_id: str, vote: ReplicaVote):
        """Record a vote from a replica"""
        self.votes[replica_id] = vote
        if vote == ReplicaVote.ACK:
            self.prepare_acks += 1
        elif vote == ReplicaVote.NACK:
            self.prepare_nacks += 1
        elif vote == ReplicaVote.TIMEOUT:
            self.prepare_timeouts += 1


class CoordinatedCommitManager:
    """
    Manages Two-Phase Commit protocol for atomic operations.
    
    Ensures that withdrawals are either applied to all replicas or none.
    
    Protocol Flow:
    1. PREPARE: Coordinator sends lock request + validate to all replicas
       - Replicas lock account and validate balance
       - Replicas respond with ACK (can commit) or NACK (cannot commit)
    
    2. COMMIT/ROLLBACK: Based on votes:
       - All ACKs: Send COMMIT to all
       - Any NACK or timeout: Send ROLLBACK to all
    
    3. Recovery: If coordinator fails during commit phase,
       replicas timeout and automatically rollback locked transactions
    """
    
    def __init__(self, node_id: str, timeout_sec: int = 5, quorum_percent: float = 0.66):
        """
        Initialize coordinated commit manager
        
        Args:
            node_id: This node's ID (coordinator)
            timeout_sec: Timeout for replica responses
            quorum_percent: Percentage of replicas needed for consensus (0.66 = 66%)
        """
        self.node_id = node_id
        self.timeout_sec = timeout_sec
        self.quorum_percent = quorum_percent
        
        # Active transactions
        self.transactions: Dict[str, CommitTransaction] = {}
        
        # Locks held by transactions (for deadlock detection)
        self.account_locks: Dict[int, str] = {}  # {account_id: transaction_id}
        
        # Prepare vote responses (transient storage during 2PC)
        self.prepare_votes: Dict[str, Dict[str, ReplicaVote]] = {}  # {txn_id: {replica_id: vote}}
        
        logger.info(f"Coordinated commit manager initialized for {node_id}")
    
    def create_transaction(
        self,
        account_id: int,
        amount: Decimal,
        request_id: str,
        replica_ids: List[str],
    ) -> Tuple[bool, str, str]:
        """
        Create a new coordinated transaction.
        
        Args:
            account_id: Account to withdraw from
            amount: Amount to withdraw
            request_id: Idempotency key
            replica_ids: List of replica node IDs
        
        Returns:
            (success: bool, message: str, transaction_id: str)
        """
        # Check if account is already locked
        if account_id in self.account_locks:
            existing_txn = self.account_locks[account_id]
            return False, f"Account locked by transaction {existing_txn}", ""
        
        # Create transaction
        txn_id = str(uuid.uuid4())
        txn = CommitTransaction(
            transaction_id=txn_id,
            coordinator_id=self.node_id,
            account_id=account_id,
            amount=amount,
            request_id=request_id,
        )
        
        self.transactions[txn_id] = txn
        self.account_locks[account_id] = txn_id
        self.prepare_votes[txn_id] = {}
        
        logger.info(
            f"[{self.node_id}] Created transaction {txn_id}: "
            f"account={account_id}, amount={amount}"
        )
        
        return True, f"Transaction created: {txn_id}", txn_id
    
    def record_prepare_vote(self, transaction_id: str, replica_id: str, vote: ReplicaVote):
        """
        Record a prepare phase vote from a replica.
        
        Args:
            transaction_id: Transaction ID
            replica_id: ID of replica that voted
            vote: The vote (ACK, NACK, or TIMEOUT)
        """
        if transaction_id not in self.transactions:
            logger.warning(f"Vote recorded for unknown transaction: {transaction_id}")
            return
        
        txn = self.transactions[transaction_id]
        txn.add_vote(replica_id, vote)
        
        if transaction_id in self.prepare_votes:
            self.prepare_votes[transaction_id][replica_id] = vote
        
        logger.debug(
            f"[{self.node_id}] Recorded {vote} from {replica_id} for txn {transaction_id}"
        )
    
    def can_commit(self, transaction_id: str, total_replicas: int) -> Tuple[bool, str]:
        """
        Determine if a transaction can be committed.
        
        Criteria:
        - All votes received (no timeouts)
        - All votes are ACK (no NACK)
        - Quorum threshold met (default 66%)
        
        Args:
            transaction_id: Transaction ID
            total_replicas: Total number of replicas in system
        
        Returns:
            (can_commit: bool, reason: str)
        """
        if transaction_id not in self.transactions:
            return False, "Transaction not found"
        
        txn = self.transactions[transaction_id]
        required_acks = max(1, int(total_replicas * self.quorum_percent))
        
        # Check for any NACKs (immediate failure)
        if txn.prepare_nacks > 0:
            return False, f"Received {txn.prepare_nacks} NACK votes"
        
        # Check for timeouts (failure to achieve consensus)
        if txn.prepare_timeouts > 0:
            return False, f"Received {txn.prepare_timeouts} timeout responses"
        
        # Check quorum
        if txn.prepare_acks < required_acks:
            return False, f"Not enough ACKs ({txn.prepare_acks}/{required_acks})"
        
        return True, "All replicas prepared"
    
    def commit_transaction(self, transaction_id: str) -> Tuple[bool, str]:
        """
        Move transaction to COMMIT phase.
        
        Args:
            transaction_id: Transaction ID
        
        Returns:
            (success: bool, message: str)
        """
        if transaction_id not in self.transactions:
            return False, "Transaction not found"
        
        txn = self.transactions[transaction_id]
        
        if txn.status != CommitPhase.PREPARE:
            return False, f"Transaction not in PREPARE phase (current: {txn.status})"
        
        txn.status = CommitPhase.COMMIT
        
        logger.info(
            f"[{self.node_id}] Transaction {transaction_id} moved to COMMIT phase"
        )
        
        return True, "Transaction committed"
    
    def rollback_transaction(self, transaction_id: str, reason: str = "") -> Tuple[bool, str]:
        """
        Rollback a transaction.
        
        Args:
            transaction_id: Transaction ID
            reason: Reason for rollback
        
        Returns:
            (success: bool, message: str)
        """
        if transaction_id not in self.transactions:
            return False, "Transaction not found"
        
        txn = self.transactions[transaction_id]
        txn.status = CommitPhase.ROLLBACK
        
        # Release account lock
        if txn.account_id in self.account_locks:
            del self.account_locks[txn.account_id]
        
        logger.info(
            f"[{self.node_id}] Transaction {transaction_id} rolled back. Reason: {reason}"
        )
        
        return True, f"Transaction rolled back: {reason}"
    
    def finalize_transaction(self, transaction_id: str) -> Tuple[bool, str]:
        """
        Finalize a transaction (clean up locks and state).
        
        Args:
            transaction_id: Transaction ID
        
        Returns:
            (success: bool, message: str)
        """
        if transaction_id not in self.transactions:
            return False, "Transaction not found"
        
        txn = self.transactions[transaction_id]
        
        # Release account lock
        if txn.account_id in self.account_locks:
            del self.account_locks[txn.account_id]
        
        # Clean up votes
        if transaction_id in self.prepare_votes:
            del self.prepare_votes[transaction_id]
        
        logger.info(
            f"[{self.node_id}] Transaction {transaction_id} finalized"
        )
        
        return True, "Transaction finalized"
    
    def get_transaction_status(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a transaction"""
        if transaction_id not in self.transactions:
            return None
        
        txn = self.transactions[transaction_id]
        return {
            'transaction_id': txn.transaction_id,
            'status': txn.status,
            'account_id': txn.account_id,
            'amount': txn.amount,
            'prepare_acks': txn.prepare_acks,
            'prepare_nacks': txn.prepare_nacks,
            'prepare_timeouts': txn.prepare_timeouts,
            'votes': {k: str(v) for k, v in txn.votes.items()},
            'created_at': txn.created_at.isoformat(),
        }
