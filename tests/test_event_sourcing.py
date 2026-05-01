"""
Comprehensive tests for distributed mobile money system
Validates:
- Event sourcing correctness
- Checkpoint consistency
- Lazy propagation (deposits)
- Strong consistency (withdrawals)
- No double spending
- Balance convergence
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import logging
from decimal import Decimal
from datetime import datetime

from src.core.checkpoint import Checkpoint, CheckpointManager
from src.core.event_log import EventLog, TransactionEvent, EventType
from src.core.distributed_node import DistributedNode
from src.core.distributed_system import DistributedSystem

logger = logging.getLogger(__name__)


class TestCheckpoint:
    """Test checkpoint functionality"""
    
    def test_checkpoint_creation(self):
        """Test creating a checkpoint"""
        cp = Checkpoint(
            balance=Decimal(1000),
            last_event_id=50,
            node_id="node_1",
            account_id=1,
        )
        
        assert cp.balance == Decimal(1000)
        assert cp.last_event_id == 50
        assert cp.node_id == "node_1"
    
    def test_checkpoint_serialization(self):
        """Test checkpoint serialization and deserialization"""
        cp = Checkpoint(
            balance=Decimal(1000),
            last_event_id=50,
            node_id="node_1",
            account_id=1,
        )
        
        # Serialize
        data = cp.to_dict()
        assert data["balance"] == "1000"
        assert data["last_event_id"] == 50
        
        # Deserialize
        cp2 = Checkpoint.from_dict(data)
        assert cp2.balance == cp.balance
        assert cp2.last_event_id == cp.last_event_id
    
    def test_checkpoint_manager(self):
        """Test checkpoint manager"""
        manager = CheckpointManager()
        
        # Create checkpoint
        cp = manager.create_checkpoint(
            balance=Decimal(500),
            last_event_id=25,
            node_id="node_1",
            account_id=1,
        )
        
        # Save and load
        manager.save_checkpoint(cp, "test_key")
        loaded = manager.load_checkpoint("test_key")
        
        assert loaded is not None
        assert loaded.balance == Decimal(500)
        assert loaded.last_event_id == 25


class TestEventLog:
    """Test event log functionality"""
    
    def test_add_event(self):
        """Test adding events to log"""
        log = EventLog()
        
        event = TransactionEvent(
            event_id=1,
            type=EventType.DEPOSIT,
            amount=Decimal(100),
            account_id=1,
        )
        
        assert log.add_event(event)
        assert len(log) == 1
        assert log.get_event(1) == event
    
    def test_duplicate_event_rejection(self):
        """Test that duplicate event IDs are rejected"""
        log = EventLog()
        
        event1 = TransactionEvent(
            event_id=1,
            type=EventType.DEPOSIT,
            amount=Decimal(100),
            account_id=1,
        )
        
        event2 = TransactionEvent(
            event_id=1,  # Same ID
            type=EventType.WITHDRAW,
            amount=Decimal(50),
            account_id=1,
        )
        
        assert log.add_event(event1)
        assert not log.add_event(event2)  # Duplicate rejected
        assert len(log) == 1
    
    def test_idempotency(self):
        """Test idempotency: duplicate request_ids rejected"""
        log = EventLog()
        
        event1 = TransactionEvent(
            event_id=1,
            type=EventType.DEPOSIT,
            amount=Decimal(100),
            account_id=1,
            request_id="req_1",
        )
        
        event2 = TransactionEvent(
            event_id=2,
            type=EventType.DEPOSIT,
            amount=Decimal(100),
            account_id=1,
            request_id="req_1",  # Same request ID
        )
        
        assert log.add_event(event1)
        assert not log.add_event(event2)  # Rejected (idempotency)
        assert len(log) == 1
    
    def test_get_events_after(self):
        """Test getting events after a specific ID"""
        log = EventLog()
        
        for i in range(1, 6):
            event = TransactionEvent(
                event_id=i,
                type=EventType.DEPOSIT,
                amount=Decimal(100),
                account_id=1,
            )
            log.add_event(event)
        
        # Get events after ID 2
        events = log.get_events_after(2)
        assert len(events) == 3  # IDs 3, 4, 5
        assert events[0].event_id == 3
        assert events[-1].event_id == 5
    
    def test_balance_computation(self):
        """Test balance computation from checkpoint + events"""
        log = EventLog()
        
        # Add deposit and withdrawal
        events = [
            TransactionEvent(
                event_id=1,
                type=EventType.DEPOSIT,
                amount=Decimal(100),
                account_id=1,
            ),
            TransactionEvent(
                event_id=2,
                type=EventType.DEPOSIT,
                amount=Decimal(50),
                account_id=1,
            ),
            TransactionEvent(
                event_id=3,
                type=EventType.WITHDRAW,
                amount=Decimal(30),
                account_id=1,
            ),
        ]
        
        for event in events:
            log.add_event(event)
        
        # Compute balance from checkpoint 0 + all events
        balance = log.compute_balance(Decimal(0), 0)
        assert balance == Decimal(120)  # 100 + 50 - 30
        
        # Compute balance from checkpoint 1 (after first deposit)
        balance = log.compute_balance(Decimal(100), 1)
        assert balance == Decimal(120)  # 100 + 50 - 30
    
    def test_merge_events(self):
        """Test merging remote events"""
        log = EventLog()
        
        # Add local event
        local_event = TransactionEvent(
            event_id=1,
            type=EventType.DEPOSIT,
            amount=Decimal(100),
            account_id=1,
        )
        log.add_event(local_event)
        
        # Merge remote events (including duplicate and new)
        remote_events = [
            TransactionEvent(
                event_id=1,  # Duplicate
                type=EventType.DEPOSIT,
                amount=Decimal(100),
                account_id=1,
            ),
            TransactionEvent(
                event_id=2,  # New
                type=EventType.DEPOSIT,
                amount=Decimal(50),
                account_id=1,
            ),
        ]
        
        merged = log.merge_events(remote_events)
        assert merged == 1  # Only 1 new event merged
        assert len(log) == 2


class TestDistributedNode:
    """Test distributed node functionality"""
    
    def test_node_creation(self):
        """Test creating a node"""
        node = DistributedNode(
            node_id="node_1",
            account_id=1,
            initial_balance=Decimal(1000),
        )
        
        assert node.node_id == "node_1"
        assert node.account_id == 1
        assert node.get_balance() == Decimal(1000)
    
    def test_deposit_lazy_propagation(self):
        """Test deposit with lazy propagation"""
        node1 = DistributedNode(node_id="node_1", account_id=1, initial_balance=Decimal(1000))
        node2 = DistributedNode(node_id="node_2", account_id=1, initial_balance=Decimal(1000))
        
        # Wire nodes
        node1.remote_nodes["node_2"] = node2
        node2.remote_nodes["node_1"] = node1
        
        # Deposit on node1
        success, msg = node1.deposit(Decimal(100), request_id="dep_1")
        assert success
        assert node1.get_balance() == Decimal(1100)
        
        # node2 should NOT have the deposit yet (lazy propagation)
        assert node2.get_balance() == Decimal(1000)
        
        # After sync, node2 should get the deposit
        node2._sync_events()
        assert node2.get_balance() == Decimal(1100)
    
    def test_withdraw_strong_consistency(self):
        """Test withdrawal with strong consistency"""
        node1 = DistributedNode(node_id="node_1", account_id=1, initial_balance=Decimal(1000))
        node2 = DistributedNode(node_id="node_2", account_id=1, initial_balance=Decimal(1000))
        
        # Wire nodes
        node1.remote_nodes["node_2"] = node2
        node2.remote_nodes["node_1"] = node1
        
        # Deposit on node2
        node2.deposit(Decimal(100), request_id="dep_1")
        
        # node1 should sync before withdrawal
        success, msg = node1.withdraw(Decimal(500), request_id="wd_1")
        assert success
        assert node1.get_balance() == Decimal(600)  # 1000 + 100 - 500
        
        # After withdrawal sync, node2 should receive withdrawal event
        assert node2.get_balance() == Decimal(600)
    
    def test_insufficient_balance(self):
        """Test withdrawal rejection for insufficient balance"""
        node = DistributedNode(node_id="node_1", account_id=1, initial_balance=Decimal(100))
        
        success, msg = node.withdraw(Decimal(200))
        assert not success
        assert "Insufficient balance" in msg
        assert node.get_balance() == Decimal(100)
    
    def test_idempotent_deposits(self):
        """Test idempotent deposits"""
        node = DistributedNode(node_id="node_1", account_id=1, initial_balance=Decimal(1000))
        
        # First deposit
        success1, msg1 = node.deposit(Decimal(100), request_id="req_1")
        assert success1
        assert node.get_balance() == Decimal(1100)
        
        # Retry with same request_id
        success2, msg2 = node.deposit(Decimal(100), request_id="req_1")
        assert not success2  # Rejected (idempotency)
        assert node.get_balance() == Decimal(1100)  # No change


class TestDistributedSystem:
    """Test distributed system coordination"""
    
    def test_system_creation(self):
        """Test creating a distributed system"""
        system = DistributedSystem(account_id=1, num_nodes=3)
        
        assert system.account_id == 1
        assert len(system.nodes) == 3
        assert all(n.account_id == 1 for n in system.nodes.values())
    
    def test_deposit_single_node(self):
        """Test deposit on single node"""
        system = DistributedSystem(account_id=1, num_nodes=1)
        
        success, msg = system.deposit("node_1", Decimal(100))
        assert success
        assert system.get_balance("node_1") == Decimal(1100)
    
    def test_convergence_after_operations(self):
        """Test that system converges after operations"""
        system = DistributedSystem(account_id=1, num_nodes=3)
        
        # Deposit on node_1
        system.deposit("node_1", Decimal(100))
        
        # Withdraw from node_2 (should sync deposits first)
        system.withdraw("node_2", Decimal(200))
        
        # Check convergence
        converged, msg = system.verify_convergence()
        assert converged, msg
    
    def test_no_double_spending(self):
        """Test that double spending is prevented"""
        system = DistributedSystem(account_id=1, num_nodes=3)
        initial_total = sum(system.get_all_balances().values())
        
        # Perform various operations
        system.deposit("node_1", Decimal(100))
        system.withdraw("node_2", Decimal(50))
        system.deposit("node_3", Decimal(75))
        system.withdraw("node_1", Decimal(100))
        
        # Total balance should remain unchanged
        final_total = sum(system.get_all_balances().values())
        assert initial_total == final_total
        
        valid, msg = system.verify_no_double_spending()
        assert valid, msg
    
    def test_multiple_deposits_then_withdraw(self):
        """
        Test edge case: deposits made on same node before withdrawal.
        Deposits should be treated as events and included in balance computation.
        """
        system = DistributedSystem(account_id=1, num_nodes=2)
        
        # Node1: deposit 100
        system.deposit("node_1", Decimal(100), request_id="dep_1")
        assert system.get_balance("node_1") == Decimal(1100)
        
        # Node1: deposit 50
        system.deposit("node_1", Decimal(50), request_id="dep_2")
        assert system.get_balance("node_1") == Decimal(1150)
        
        # Node2: withdraw 300 (should sync deposits from node1)
        success, msg = system.withdraw("node_2", Decimal(300), request_id="wd_1")
        assert success
        
        # Expected: node2 started with 1000, node1 added 150 deposits,
        # so node2 can see 1150, after withdrawal: 850
        assert system.get_balance("node_2") == Decimal(850)


# Run tests with detailed output
if __name__ == "__main__":
    # Configure logging for tests
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Run pytest with verbose output
    pytest.main([__file__, "-v", "-s"])
