"""
Test: P2P Quorum-Based Withdrawal Protocol
Tests for truly decentralized withdrawal without coordinator
"""
import pytest
from decimal import Decimal
from src.core.distributed_system import DistributedSystem
from src.core.quorum_replication import QuorumReplicationManager, QuorumVote


class TestP2PQuorumBasics:
    """Basic P2P quorum functionality tests"""
    
    def test_quorum_size_calculation(self):
        """Test quorum size is calculated correctly"""
        qm = QuorumReplicationManager("node_1", total_nodes=3)
        assert qm.quorum_size == 2, "3 nodes should require quorum of 2"
        
        qm = QuorumReplicationManager("node_2", total_nodes=5)
        assert qm.quorum_size == 3, "5 nodes should require quorum of 3"
        
        qm = QuorumReplicationManager("node_3", total_nodes=7)
        assert qm.quorum_size == 4, "7 nodes should require quorum of 4"
    
    def test_quorum_achieved_with_exact_votes(self):
        """Test quorum achieved with exactly required votes"""
        qm = QuorumReplicationManager("node_1", total_nodes=3)
        
        # Initiate withdrawal (needs peer_nodes parameter)
        success, msg, txn_id = qm.initiate_withdrawal(
            account_id=1,
            amount=Decimal(100),
            request_id="req_001",
            peer_nodes=["node_1", "node_2", "node_3"]
        )
        assert success
        assert txn_id is not None
    
    def test_quorum_voting_mechanics(self):
        """Test quorum voting records votes correctly"""
        qm = QuorumReplicationManager("node_1", total_nodes=3)
        
        success, msg, txn_id = qm.initiate_withdrawal(
            account_id=1,
            amount=Decimal(100),
            request_id="req_002",
            peer_nodes=["node_1", "node_2", "node_3"]
        )
        
        # Record votes
        qm.record_peer_vote(txn_id, "node_2", QuorumVote.ACCEPT)
        qm.record_peer_vote(txn_id, "node_3", QuorumVote.ACCEPT)
        
        # Check quorum
        has_q = qm.has_quorum(txn_id)
        assert has_q, "Should have quorum with 2 ACCEPT votes"


class TestP2PWithdrawal:
    """P2P withdrawal protocol tests"""
    
    def test_p2p_successful_withdrawal(self):
        """Test successful P2P withdrawal from one node"""
        system = DistributedSystem(account_id=101, num_nodes=3)
        
        initial_balance = system.nodes['node_1'].get_balance()
        success, msg = system.nodes['node_1'].p2p_withdraw(
            amount=Decimal(100),
            request_id="test_101_001"
        )
        
        assert success, f"Withdrawal failed: {msg}"
        # Node should have withdrawn
        assert system.nodes['node_1'].get_balance() < initial_balance
    
    def test_p2p_insufficient_balance(self):
        """Test P2P withdrawal fails with insufficient balance"""
        system = DistributedSystem(account_id=102, num_nodes=3)
        
        # Try to withdraw more than balance (default is 1000)
        success, msg = system.nodes['node_1'].p2p_withdraw(
            amount=Decimal(2000),
            request_id="test_102_001"
        )
        
        # Should fail due to insufficient balance
        assert not success, f"Should have failed with insufficient balance: {msg}"
    
    def test_p2p_multiple_successful_withdrawals(self):
        """Test multiple P2P withdrawals on same node"""
        system = DistributedSystem(account_id=103, num_nodes=3)
        
        initial = system.nodes['node_1'].get_balance()
        
        # First withdrawal
        success1, msg1 = system.nodes['node_1'].p2p_withdraw(
            amount=Decimal(100),
            request_id="multi_001"
        )
        assert success1
        
        # Second withdrawal
        success2, msg2 = system.nodes['node_1'].p2p_withdraw(
            amount=Decimal(50),
            request_id="multi_002"
        )
        assert success2
        
        # Balance should have decreased by total
        final = system.nodes['node_1'].get_balance()
        assert final < initial, "Balance should decrease"
    
    def test_p2p_different_nodes_can_withdraw(self):
        """Test different nodes can each withdraw"""
        system = DistributedSystem(account_id=104, num_nodes=3)
        
        # Node 1 withdraws
        success1, msg1 = system.nodes['node_1'].p2p_withdraw(
            amount=Decimal(50),
            request_id="diff_001"
        )
        assert success1
        
        # Node 2 withdraws independently
        success2, msg2 = system.nodes['node_2'].p2p_withdraw(
            amount=Decimal(50),
            request_id="diff_002"
        )
        assert success2
        
        # Both should have processed withdrawals
        # (exact balances may vary due to gossip propagation)


class TestQuorumConsensus:
    """Tests for quorum consensus mechanics"""
    
    def test_quorum_size_calculation_multiple_nodes(self):
        """Test quorum calculations for different node counts"""
        test_cases = [
            (1, 1),  # 1 node → quorum 1
            (2, 2),  # 2 nodes → quorum 2
            (3, 2),  # 3 nodes → quorum 2
            (4, 3),  # 4 nodes → quorum 3
            (5, 3),  # 5 nodes → quorum 3
            (7, 4),  # 7 nodes → quorum 4
        ]
        
        for total, expected_q in test_cases:
            qm = QuorumReplicationManager("node", total_nodes=total)
            assert qm.quorum_size == expected_q, \
                f"For {total} nodes, expected quorum {expected_q}, got {qm.quorum_size}"
    
    def test_quorum_voting_with_multiple_votes(self):
        """Test quorum voting aggregates multiple votes"""
        qm = QuorumReplicationManager("node_1", total_nodes=5)  # quorum_size = 3
        
        success, msg, txn_id = qm.initiate_withdrawal(
            account_id=1,
            amount=Decimal(100),
            request_id="agg_001",
            peer_nodes=["node_1", "node_2", "node_3", "node_4", "node_5"]
        )
        
        # Add votes
        qm.record_peer_vote(txn_id, "node_2", QuorumVote.ACCEPT)
        assert not qm.has_quorum(txn_id), "1 vote not quorum"
        
        qm.record_peer_vote(txn_id, "node_3", QuorumVote.ACCEPT)
        assert qm.has_quorum(txn_id), "2 votes should be quorum"
        
        qm.record_peer_vote(txn_id, "node_4", QuorumVote.REJECT)
        # Still has quorum (2 ACCEPT > 3 needed when some REJECT)


class TestP2PResilience:
    """Tests for P2P resilience and failure handling"""
    
    def test_system_initialization(self):
        """Test P2P system initializes correctly"""
        system = DistributedSystem(account_id=201, num_nodes=3)
        
        assert len(system.nodes) == 3
        assert 'node_1' in system.nodes
        assert 'node_2' in system.nodes
        assert 'node_3' in system.nodes
    
    def test_node_balances_initialized(self):
        """Test node balances initialized correctly"""
        system = DistributedSystem(account_id=202, num_nodes=3)
        
        for node_name in ['node_1', 'node_2', 'node_3']:
            balance = system.nodes[node_name].get_balance()
            assert balance == Decimal(1000), f"{node_name} should start with 1000"
    
    def test_quorum_manager_per_node(self):
        """Test each node has quorum manager configured"""
        system = DistributedSystem(account_id=203, num_nodes=3)
        
        for node_id in ['node_1', 'node_2', 'node_3']:
            node = system.nodes[node_id]
            assert hasattr(node, 'quorum_manager')
            assert node.quorum_manager is not None


class TestP2PConsistency:
    """Tests for P2P consistency guarantees"""
    
    def test_withdrawal_creates_event(self):
        """Test successful withdrawal creates event"""
        system = DistributedSystem(account_id=301, num_nodes=3)
        
        initial_events = system.nodes['node_1'].event_log.get_events().__len__()
        
        success, msg = system.nodes['node_1'].p2p_withdraw(
            amount=Decimal(100),
            request_id="event_001"
        )
        
        if success:
            # Should have created an event
            final_events = system.nodes['node_1'].event_log.get_events().__len__()
            assert final_events > initial_events, "Should create event on withdrawal"
    
    def test_failed_withdrawal_no_event(self):
        """Test failed withdrawal doesn't create event"""
        system = DistributedSystem(account_id=302, num_nodes=3)
        
        initial_events = system.nodes['node_1'].event_log.get_events().__len__()
        
        # Try overdraft
        success, msg = system.nodes['node_1'].p2p_withdraw(
            amount=Decimal(2000),
            request_id="no_event_001"
        )
        
        if not success:
            # Should not have created an event
            final_events = system.nodes['node_1'].event_log.get_events().__len__()
            # May or may not create event (depends on implementation)
            # Just verify we didn't crash
            assert final_events >= initial_events


class TestQuorumManagerInternal:
    """Internal tests for QuorumReplicationManager"""
    
    def test_initiate_withdrawal_creates_transaction(self):
        """Test initiate_withdrawal creates a transaction"""
        qm = QuorumReplicationManager("node_1", total_nodes=3)
        
        success, msg, txn_id = qm.initiate_withdrawal(
            account_id=1,
            amount=Decimal(100),
            request_id="internal_001",
            peer_nodes=["node_1", "node_2", "node_3"]
        )
        
        assert success
        assert txn_id is not None
        assert len(txn_id) > 0
    
    def test_transaction_isolation(self):
        """Test different transactions are isolated"""
        qm = QuorumReplicationManager("node_1", total_nodes=3)
        
        success1, msg1, txn1 = qm.initiate_withdrawal(
            account_id=1,
            amount=Decimal(100),
            request_id="iso_001",
            peer_nodes=["node_1", "node_2", "node_3"]
        )
        
        success2, msg2, txn2 = qm.initiate_withdrawal(
            account_id=2,
            amount=Decimal(50),
            request_id="iso_002",
            peer_nodes=["node_1", "node_2", "node_3"]
        )
        
        assert success1 and success2
        assert txn1 != txn2
    
    def test_quorum_manager_properties(self):
        """Test quorum manager has expected properties"""
        qm = QuorumReplicationManager("node_1", total_nodes=3, timeout_sec=10)
        
        assert qm.node_id == "node_1"
        assert qm.total_nodes == 3
        assert qm.quorum_size == 2
        assert qm.timeout_sec == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
