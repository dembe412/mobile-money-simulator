"""
Quorum-Based Replication Protocol (P2P Version)
No designated coordinator - any node can initiate withdrawals
Uses quorum writes for consistency without centralization
"""
from enum import Enum
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import logging
import uuid

logger = logging.getLogger(__name__)


class QuorumVote(str, Enum):
    """Vote in quorum consensus"""
    ACCEPT = "accept"      # Node accepts withdrawal
    REJECT = "reject"      # Node rejects withdrawal
    TIMEOUT = "timeout"    # Node did not respond


@dataclass
class QuorumTransaction:
    """Represents a quorum-based transaction"""
    transaction_id: str
    initiator_id: str         # Which node started this (any node!)
    account_id: int
    amount: Decimal
    request_id: str
    
    # Voting state
    votes: Dict[str, QuorumVote] = None  # {node_id: vote}
    accept_votes: int = 0
    reject_votes: int = 0
    timeout_votes: int = 0
    
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.votes is None:
            self.votes = {}
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    def add_vote(self, node_id: str, vote: QuorumVote):
        """Record a vote from a node"""
        self.votes[node_id] = vote
        if vote == QuorumVote.ACCEPT:
            self.accept_votes += 1
        elif vote == QuorumVote.REJECT:
            self.reject_votes += 1
        elif vote == QuorumVote.TIMEOUT:
            self.timeout_votes += 1


class QuorumReplicationManager:
    """
    P2P Quorum-Based Replication - No Coordinator
    
    Protocol:
    1. Any node can initiate a withdrawal
    2. Send withdrawal to quorum of nodes
    3. If quorum accepts: apply + gossip
    4. If quorum rejects: rollback
    
    Key benefit: No single coordinator bottleneck
    """
    
    def __init__(
        self,
        node_id: str,
        quorum_size: int = None,
        total_nodes: int = 3,
        timeout_sec: int = 5
    ):
        """
        Initialize quorum replication manager (P2P version)
        
        Args:
            node_id: This node's ID
            quorum_size: Number of nodes needed for quorum
                        If None: calculated as ceil(total_nodes / 2 + 0.5) = majority + 1
            total_nodes: Total nodes in system
            timeout_sec: Timeout for peer responses
        """
        self.node_id = node_id
        self.total_nodes = total_nodes
        self.timeout_sec = timeout_sec
        
        # Calculate quorum size (majority)
        if quorum_size is None:
            # For 3 nodes: need 2 (majority)
            # For 5 nodes: need 3 (majority)
            self.quorum_size = (total_nodes // 2) + 1
        else:
            self.quorum_size = quorum_size
        
        # Active transactions initiated by this node
        self.transactions: Dict[str, QuorumTransaction] = {}
        
        # Track which nodes voted in each transaction
        self.transaction_votes: Dict[str, Dict[str, QuorumVote]] = {}
        
        # Locks on accounts being withdrawn from: {account_id: txn_id}
        self.account_locks: Dict[int, str] = {}
        
        logger.info(
            f"[{self.node_id}] Quorum manager initialized: "
            f"quorum_size={self.quorum_size}, total_nodes={self.total_nodes}"
        )
    
    def initiate_withdrawal(
        self,
        account_id: int,
        amount: Decimal,
        request_id: str,
        peer_nodes: List[str],
    ) -> Tuple[bool, str, str]:
        """
        P2P: Initiate withdrawal from this node (can be any node!)
        
        Args:
            account_id: Account to withdraw from
            amount: Amount to withdraw
            request_id: Idempotency key
            peer_nodes: List of all peer node IDs (including self)
        
        Returns:
            (success: bool, message: str, transaction_id: str)
        """
        # Check if account already locked
        if account_id in self.account_locks:
            existing_txn = self.account_locks[account_id]
            return False, f"Account locked by transaction {existing_txn}", ""
        
        # Create transaction
        txn_id = str(uuid.uuid4())
        txn = QuorumTransaction(
            transaction_id=txn_id,
            initiator_id=self.node_id,  # THIS node is initiating
            account_id=account_id,
            amount=amount,
            request_id=request_id,
        )
        
        self.transactions[txn_id] = txn
        self.account_locks[account_id] = txn_id
        self.transaction_votes[txn_id] = {}
        
        logger.info(
            f"[{self.node_id}] Initiated withdrawal txn {txn_id}: "
            f"account={account_id}, amount={amount}, peers={len(peer_nodes)}"
        )
        
        return True, f"Withdrawal initiated: {txn_id}", txn_id
    
    def request_withdrawal_from_peer(
        self,
        transaction_id: str,
        account_id: int,
        amount: Decimal,
        request_id: str,
        initiator_id: str,
    ) -> QuorumVote:
        """
        PEER SIDE: Receive withdrawal request from another peer
        
        This node votes YES (ACCEPT) or NO (REJECT) for the withdrawal
        WITHOUT necessarily applying it locally yet.
        
        Args:
            transaction_id: Transaction ID from initiator
            account_id: Account to withdraw from
            amount: Amount to withdraw
            request_id: Idempotency key
            initiator_id: Which peer initiated this
        
        Returns:
            QuorumVote: ACCEPT, REJECT, or TIMEOUT
        """
        try:
            # Validate: Do we have sufficient balance?
            # (In real implementation, fetch from local state)
            
            # For now, simplified: assume yes unless already locked
            if account_id in self.account_locks:
                # Account is locked by another transaction
                logger.warning(
                    f"[{self.node_id}] Rejecting txn {transaction_id}: "
                    f"account {account_id} is locked"
                )
                return QuorumVote.REJECT
            
            # Temporary lock during voting phase
            temp_lock_txn = f"temp_{transaction_id}"
            self.account_locks[account_id] = temp_lock_txn
            
            logger.info(
                f"[{self.node_id}] Accepted withdrawal vote for txn {transaction_id} "
                f"from {initiator_id}: amount={amount}"
            )
            
            return QuorumVote.ACCEPT
        
        except Exception as e:
            logger.error(f"[{self.node_id}] Error in withdrawal vote: {e}")
            return QuorumVote.REJECT
    
    def record_peer_vote(
        self,
        transaction_id: str,
        peer_id: str,
        vote: QuorumVote
    ):
        """
        INITIATOR SIDE: Record vote from a peer
        
        Args:
            transaction_id: Transaction ID
            peer_id: Which peer voted
            vote: Their vote (ACCEPT, REJECT, or TIMEOUT)
        """
        if transaction_id not in self.transactions:
            logger.warning(f"Vote recorded for unknown transaction: {transaction_id}")
            return
        
        txn = self.transactions[transaction_id]
        txn.add_vote(peer_id, vote)
        
        if transaction_id in self.transaction_votes:
            self.transaction_votes[transaction_id][peer_id] = vote
        
        logger.debug(
            f"[{self.node_id}] Peer {peer_id} voted {vote} for txn {transaction_id}"
        )
    
    def has_quorum(self, transaction_id: str) -> Tuple[bool, str]:
        """
        Check if we have quorum of ACCEPTS
        
        Quorum = majority of nodes
        
        Args:
            transaction_id: Transaction ID
        
        Returns:
            (has_quorum: bool, reason: str)
        """
        if transaction_id not in self.transactions:
            return False, "Transaction not found"
        
        txn = self.transactions[transaction_id]
        
        # Need quorum_size ACCEPT votes
        if txn.accept_votes >= self.quorum_size:
            return True, f"Quorum achieved ({txn.accept_votes}/{self.quorum_size})"
        
        # Any REJECT? Can't commit
        if txn.reject_votes > 0:
            return False, f"Received {txn.reject_votes} REJECT votes"
        
        # Not enough votes?
        total_votes = len(txn.votes)
        if total_votes < self.quorum_size:
            return False, f"Not enough votes yet ({total_votes}/{self.quorum_size})"
        
        return False, "Quorum not achieved"
    
    def apply_withdrawal(self, transaction_id: str) -> Tuple[bool, str]:
        """
        Apply withdrawal locally after quorum achieved
        
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
        
        logger.info(
            f"[{self.node_id}] Applied withdrawal txn {transaction_id}: "
            f"account={txn.account_id}, amount={txn.amount}"
        )
        
        return True, "Withdrawal applied"
    
    def reject_withdrawal(self, transaction_id: str, reason: str = "") -> Tuple[bool, str]:
        """
        Reject withdrawal (quorum not achieved)
        
        Args:
            transaction_id: Transaction ID
            reason: Reason for rejection
        
        Returns:
            (success: bool, message: str)
        """
        if transaction_id not in self.transactions:
            return False, "Transaction not found"
        
        txn = self.transactions[transaction_id]
        
        # Release account lock
        if txn.account_id in self.account_locks:
            del self.account_locks[txn.account_id]
        
        logger.warning(
            f"[{self.node_id}] Rejected withdrawal txn {transaction_id}: {reason}"
        )
        
        return True, f"Withdrawal rejected: {reason}"
    
    def get_transaction_status(self, transaction_id: str) -> Optional[Dict]:
        """Get status of a transaction"""
        if transaction_id not in self.transactions:
            return None
        
        txn = self.transactions[transaction_id]
        return {
            'transaction_id': txn.transaction_id,
            'initiator_id': txn.initiator_id,
            'account_id': txn.account_id,
            'amount': str(txn.amount),
            'accept_votes': txn.accept_votes,
            'reject_votes': txn.reject_votes,
            'timeout_votes': txn.timeout_votes,
            'votes': {k: str(v) for k, v in txn.votes.items()},
            'timestamp': txn.timestamp.isoformat(),
        }
