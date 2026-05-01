"""
Distributed System Coordinator
Manages multiple distributed nodes and ensures system-wide consistency
"""
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import logging

from src.core.distributed_node import DistributedNode

logger = logging.getLogger(__name__)


class DistributedSystem:
    """
    Coordinates multiple distributed nodes.
    
    Provides:
    - Node creation and management
    - Inter-node communication
    - System-wide state inspection
    - Consistency verification
    """
    
    def __init__(self, account_id: int = 1, num_nodes: int = 3):
        """
        Initialize distributed system.
        
        Args:
            account_id: Account ID managed by the system
            num_nodes: Number of nodes to create
        """
        self.account_id = account_id
        self.nodes: Dict[str, DistributedNode] = {}
        self.num_nodes = num_nodes
        
        # Create nodes
        for i in range(1, num_nodes + 1):
            node_id = f"node_{i}"
            node = DistributedNode(
                node_id=node_id,
                account_id=account_id,
                initial_balance=Decimal(1000),  # Start with 1000 each
                min_replicas=max(1, num_nodes // 2),
            )
            self.nodes[node_id] = node
        
        # Wire up inter-node communication
        self._wire_nodes()
        
        logger.info(f"Distributed system initialized with {num_nodes} nodes")
    
    def _wire_nodes(self):
        """Connect nodes so they can communicate with each other"""
        for node_id, node in self.nodes.items():
            for remote_id, remote_node in self.nodes.items():
                if node_id != remote_id:
                    node.remote_nodes[remote_id] = remote_node
            logger.debug(f"Node {node_id} wired to {len(node.remote_nodes)} remote nodes")
    
    def get_node(self, node_id: str) -> Optional[DistributedNode]:
        """Get node by ID"""
        return self.nodes.get(node_id)
    
    def deposit(self, node_id: str, amount: Decimal, request_id: str = "") -> Tuple[bool, str]:
        """
        Perform deposit on specific node.
        
        Args:
            node_id: Node to perform deposit on
            amount: Amount to deposit
            request_id: Optional request ID for idempotency
            
        Returns:
            (success: bool, message: str)
        """
        node = self.get_node(node_id)
        if not node:
            return False, f"Node {node_id} not found"
        
        return node.deposit(amount, request_id)
    
    def withdraw(self, node_id: str, amount: Decimal, request_id: str = "") -> Tuple[bool, str]:
        """
        Perform withdrawal on specific node.
        
        Args:
            node_id: Node to perform withdrawal on
            amount: Amount to withdraw
            request_id: Optional request ID for idempotency
            
        Returns:
            (success: bool, message: str)
        """
        node = self.get_node(node_id)
        if not node:
            return False, f"Node {node_id} not found"
        
        return node.withdraw(amount, request_id)
    
    def get_balance(self, node_id: str) -> Optional[Decimal]:
        """
        Get balance on specific node.
        
        Args:
            node_id: Node ID
            
        Returns:
            Balance or None if node not found
        """
        node = self.get_node(node_id)
        if not node:
            return None
        
        return node.get_balance()
    
    def get_all_balances(self) -> Dict[str, Decimal]:
        """
        Get balances from all nodes.
        
        Returns:
            Dict mapping node_id to balance
        """
        return {node_id: node.get_balance() for node_id, node in self.nodes.items()}
    
    def verify_convergence(self, tolerance: Decimal = Decimal(0)) -> Tuple[bool, str]:
        """
        Verify that all nodes have converged to same balance.
        
        Args:
            tolerance: Allowed difference (for eventual consistency checking)
            
        Returns:
            (converged: bool, message: str)
        """
        balances = self.get_all_balances()
        
        if not balances:
            return False, "No nodes in system"
        
        # Get first balance as reference
        reference_balance = list(balances.values())[0]
        
        # Check all balances match
        for node_id, balance in balances.items():
            diff = abs(balance - reference_balance)
            if diff > tolerance:
                return (
                    False,
                    f"Convergence failed: {node_id} has {balance}, "
                    f"expected {reference_balance} (diff={diff})",
                )
        
        return True, f"All nodes converged to balance={reference_balance}"
    
    def verify_no_double_spending(self) -> Tuple[bool, str]:
        """
        Verify no double spending by checking total balance doesn't increase/decrease.
        
        Initial state: all nodes have 1000 each = 3000 total
        After operations: total should remain 3000 (deposits/withdrawals within system)
        
        Returns:
            (valid: bool, message: str)
        """
        total_balance = sum(self.get_all_balances().values())
        expected_total = Decimal(1000) * self.num_nodes
        
        if total_balance != expected_total:
            return (
                False,
                f"Double spending detected: total_balance={total_balance}, "
                f"expected={expected_total}",
            )
        
        return True, f"No double spending: total_balance={total_balance}"
    
    def get_system_state(self) -> Dict:
        """
        Get complete system state for inspection.
        
        Returns:
            Dictionary with system state
        """
        balances = self.get_all_balances()
        total_balance = sum(balances.values())
        
        return {
            "account_id": self.account_id,
            "num_nodes": self.num_nodes,
            "balances": {node_id: str(balance) for node_id, balance in balances.items()},
            "total_balance": str(total_balance),
            "convergence": self.verify_convergence()[0],
            "no_double_spending": self.verify_no_double_spending()[0],
            "nodes": {node_id: node.get_state() for node_id, node in self.nodes.items()},
        }
    
    def print_state(self):
        """Pretty print system state"""
        print("\n" + "=" * 70)
        print("DISTRIBUTED SYSTEM STATE")
        print("=" * 70)
        
        balances = self.get_all_balances()
        for node_id in sorted(balances.keys()):
            balance = balances[node_id]
            print(f"  {node_id:15} : {balance:>10}")
        
        total_balance = sum(balances.values())
        print("-" * 70)
        print(f"  {'Total':15} : {total_balance:>10}")
        print("=" * 70 + "\n")
    
    def __repr__(self) -> str:
        balances = self.get_all_balances()
        total = sum(balances.values()) if balances else Decimal(0)
        return (
            f"DistributedSystem(account={self.account_id}, "
            f"nodes={self.num_nodes}, total_balance={total})"
        )
