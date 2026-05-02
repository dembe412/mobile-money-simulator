"""
Test: P2P Quorum-Based Withdrawal Protocol
Simplified tests focusing on core functionality
"""
import pytest
from decimal import Decimal
from src.core.distributed_system import DistributedSystem
from src.core.quorum_replication import QuorumReplicationManager, QuorumVote


class TestQuorumSizeCalculation:
    """Test quorum size calculation"""
    
    def test_3_nodes_quorum_2(self):
        """3 nodes should require quorum of 2"""
        qm = QuorumReplicationManager("node_1", total_nodes=3)
        assert qm.quorum_size == 2
    
    def test_5_nodes_quorum_3(self):
        """5 nodes should require quorum of 3"""
        qm = QuorumReplicationManager("node_1", total_nodes=5)
        assert qm.quorum_size == 3
    
    def test_7_nodes_quorum_4(self):
        """7 nodes should require quorum of 4"""
        qm = QuorumReplicationManager("node_1", total_nodes=7)
        assert qm.quorum_size == 4


class TestP2PWithdrawalBasic:
    """Test basic P2P withdrawal functionality"""
    
    def test_successful_withdrawal(self):
        """Successful P2P withdrawal"""
        system = DistributedSystem(account_id=101, num_nodes=3)
        initial = system.nodes['node_1'].get_balance()
        
        success, msg = system.nodes['node_1'].p2p_withdraw(
            amount=Decimal(100),
            request_id="basic_001"
        )
        
        assert success, f"Withdrawal failed: {msg}"
        final = system.nodes['node_1'].get_balance()
        assert final < initial, "Balance should decrease"
    
    def test_withdrawal_insufficient_balance(self):
        """P2P withdrawal fails with insufficient balance"""
        system = DistributedSystem(account_id=102, num_nodes=3)
        
        success, msg = system.nodes['node_1'].p2p_withdraw(
            amount=Decimal(5000),
            request_id="insufficient_001"
        )
        
        assert not success, "Should fail with insufficient balance"
    
    def test_multiple_nodes_can_withdraw(self):
        """Multiple nodes can initiate withdrawals"""
        system = DistributedSystem(account_id=103, num_nodes=3)
        
        s1, m1 = system.nodes['node_1'].p2p_withdraw(Decimal(50), "multi_001")
        s2, m2 = system.nodes['node_2'].p2p_withdraw(Decimal(50), "multi_002")
        s3, m3 = system.nodes['node_3'].p2p_withdraw(Decimal(50), "multi_003")
        
        assert s1 and s2 and s3, "All nodes should be able to withdraw"


class TestQuorumTransactionManager:
    """Test quorum transaction management"""
    
    def test_initiate_withdrawal_creates_txn(self):
        """initiate_withdrawal creates a transaction"""
        qm = QuorumReplicationManager("node_1", total_nodes=3)
        
        success, msg, txn_id = qm.initiate_withdrawal(
            account_id=1,
            amount=Decimal(100),
            request_id="txn_001",
            peer_nodes=["node_1", "node_2", "node_3"]
        )
        
        assert success
        assert txn_id is not None
        assert len(txn_id) > 0
    
    def test_quorum_manager_properties(self):
        """Quorum manager has correct properties"""
        qm = QuorumReplicationManager("node_test", total_nodes=5, timeout_sec=10)
        
        assert qm.node_id == "node_test"
        assert qm.total_nodes == 5
        assert qm.quorum_size == 3
        assert qm.timeout_sec == 10


class TestP2PSystemSetup:
    """Test P2P system initialization"""
    
    def test_3_node_system_initialized(self):
        """3-node system initializes correctly"""
        system = DistributedSystem(account_id=201, num_nodes=3)
        
        assert len(system.nodes) == 3
        assert all(node_id in system.nodes for node_id in ['node_1', 'node_2', 'node_3'])
    
    def test_initial_balances_correct(self):
        """Initial balances are set correctly"""
        system = DistributedSystem(account_id=202, num_nodes=3)
        
        for node_name in ['node_1', 'node_2', 'node_3']:
            assert system.nodes[node_name].get_balance() == Decimal(1000)
    
    def test_nodes_have_quorum_manager(self):
        """Each node has quorum manager"""
        system = DistributedSystem(account_id=203, num_nodes=3)
        
        for node_name in ['node_1', 'node_2', 'node_3']:
            node = system.nodes[node_name]
            assert hasattr(node, 'quorum_manager')
            assert node.quorum_manager is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
