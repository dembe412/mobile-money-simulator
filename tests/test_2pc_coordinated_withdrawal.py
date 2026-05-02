"""
Test suite for Two-Phase Commit (2PC) Coordinated Withdrawals
Validates all aspects of the 2PC protocol implementation
"""
import unittest
from decimal import Decimal
import logging

logging.basicConfig(level=logging.INFO)

from src.core.distributed_system import DistributedSystem
from src.core.coordinated_commit import CoordinatedCommitManager, ReplicaVote


class Test2PCCoordinatedWithdrawal(unittest.TestCase):
    """Test cases for 2PC protocol"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.system = DistributedSystem(account_id=1, num_nodes=3)
    
    def test_successful_coordinated_withdrawal(self):
        """Test 1: Successful coordinated withdrawal with all replicas agreeing"""
        node_1 = self.system.get_node('node_1')
        initial_balance = Decimal(1000)
        withdraw_amount = Decimal(100)
        
        # Verify initial state
        self.assertEqual(node_1.get_balance(), initial_balance)
        
        # Execute coordinated withdrawal
        success, message = node_1.coordinated_withdraw(
            amount=withdraw_amount,
            request_id="test_001"
        )
        
        # Assertions
        self.assertTrue(success, f"Withdrawal should succeed: {message}")
        
        # Verify all nodes have consistent state
        expected_balance = initial_balance - withdraw_amount
        for node_id in self.system.nodes.keys():
            node = self.system.get_node(node_id)
            actual_balance = node.get_balance()
            self.assertEqual(
                actual_balance, expected_balance,
                f"{node_id} balance mismatch. Expected {expected_balance}, got {actual_balance}"
            )
    
    def test_insufficient_balance_causes_rollback(self):
        """Test 2: Insufficient balance on one replica causes all to rollback"""
        # Manually deplete node_2
        node_2 = self.system.get_node('node_2')
        node_2.checkpoint.balance = Decimal(50)
        
        node_1 = self.system.get_node('node_1')
        initial_balance_1 = node_1.get_balance()
        initial_balance_2 = node_2.get_balance()
        
        # Try to withdraw 100 (should fail because node_2 only has 50)
        withdraw_amount = Decimal(100)
        success, message = node_1.coordinated_withdraw(
            amount=withdraw_amount,
            request_id="test_002"
        )
        
        # Should fail
        self.assertFalse(success, f"Withdrawal should fail: {message}")
        
        # Verify all balances unchanged (rollback succeeded)
        self.assertEqual(node_1.get_balance(), initial_balance_1)
        self.assertEqual(node_2.get_balance(), initial_balance_2)
        self.assertEqual(self.system.get_node('node_3').get_balance(), Decimal(1000))
    
    def test_multiple_sequential_withdrawals(self):
        """Test 3: Multiple sequential withdrawals maintain consistency"""
        node_1 = self.system.get_node('node_1')
        
        # Withdrawal 1
        success1, _ = node_1.coordinated_withdraw(
            amount=Decimal(100),
            request_id="test_003_1"
        )
        self.assertTrue(success1)
        
        # Check balance after withdrawal 1
        expected_balance_1 = Decimal(900)
        for node in self.system.nodes.values():
            self.assertEqual(node.get_balance(), expected_balance_1)
        
        # Withdrawal 2
        success2, _ = node_1.coordinated_withdraw(
            amount=Decimal(200),
            request_id="test_003_2"
        )
        self.assertTrue(success2)
        
        # Check final balance
        expected_balance_2 = Decimal(700)
        for node in self.system.nodes.values():
            self.assertEqual(node.get_balance(), expected_balance_2)
    
    def test_locks_prevent_double_spending(self):
        """Test 4: Locked funds prevent double-spending across replicas"""
        node_1 = self.system.get_node('node_1')
        
        # In prepare phase, funds should be locked
        # Simulate prepare phase by directly calling prepare
        txn_id = "test_004_txn"
        vote = node_1.prepare_for_coordinated_withdraw(
            transaction_id=txn_id,
            account_id=1,
            amount=Decimal(100),
            request_id="test_004"
        )
        
        # Should succeed
        self.assertEqual(vote, ReplicaVote.ACK)
        
        # Verify funds are locked
        self.assertIn(txn_id, node_1.locked_funds)
        self.assertEqual(node_1.locked_funds[txn_id], Decimal(100))
        
        # Try to prepare another transaction for same amount
        # Should fail because funds are locked
        vote2 = node_1.prepare_for_coordinated_withdraw(
            transaction_id="test_004_txn_2",
            account_id=1,
            amount=Decimal(950),  # 1000 - 100 (locked)
            request_id="test_004_2"
        )
        
        # Should fail (insufficient available balance)
        self.assertEqual(vote2, ReplicaVote.NACK)
    
    def test_rollback_clears_locks(self):
        """Test 5: Rollback properly releases locks"""
        node_1 = self.system.get_node('node_1')
        txn_id = "test_005_txn"
        
        # Prepare (locks funds)
        vote = node_1.prepare_for_coordinated_withdraw(
            transaction_id=txn_id,
            account_id=1,
            amount=Decimal(100),
            request_id="test_005"
        )
        self.assertEqual(vote, ReplicaVote.ACK)
        self.assertIn(txn_id, node_1.locked_funds)
        
        # Rollback (should release locks)
        success, _ = node_1.rollback_coordinated_withdraw(txn_id)
        self.assertTrue(success)
        
        # Verify locks cleared
        self.assertNotIn(txn_id, node_1.locked_funds)
        self.assertNotIn(txn_id, node_1.prepared_transactions)
    
    def test_coordinated_commit_manager_tracks_votes(self):
        """Test 6: CoordinatedCommitManager correctly tracks votes"""
        manager = CoordinatedCommitManager("node_1")
        
        # Create transaction
        success, msg, txn_id = manager.create_transaction(
            account_id=1,
            amount=Decimal(100),
            request_id="test_006",
            replica_ids=["node_1", "node_2", "node_3"]
        )
        self.assertTrue(success)
        
        # Record votes
        manager.record_prepare_vote(txn_id, "node_1", ReplicaVote.ACK)
        manager.record_prepare_vote(txn_id, "node_2", ReplicaVote.ACK)
        manager.record_prepare_vote(txn_id, "node_3", ReplicaVote.ACK)
        
        # Check can_commit
        total_replicas = 3
        can_commit, reason = manager.can_commit(txn_id, total_replicas)
        self.assertTrue(can_commit, f"Should be able to commit: {reason}")
        
        # Verify vote counts
        txn = manager.transactions[txn_id]
        self.assertEqual(txn.prepare_acks, 3)
        self.assertEqual(txn.prepare_nacks, 0)
        self.assertEqual(txn.prepare_timeouts, 0)
    
    def test_quorum_voting_with_nack(self):
        """Test 7: Even one NACK prevents commit"""
        manager = CoordinatedCommitManager("node_1")
        
        success, msg, txn_id = manager.create_transaction(
            account_id=1,
            amount=Decimal(100),
            request_id="test_007",
            replica_ids=["node_1", "node_2", "node_3"]
        )
        
        # Record votes: 2 ACK, 1 NACK
        manager.record_prepare_vote(txn_id, "node_1", ReplicaVote.ACK)
        manager.record_prepare_vote(txn_id, "node_2", ReplicaVote.NACK)  # One NACK!
        manager.record_prepare_vote(txn_id, "node_3", ReplicaVote.ACK)
        
        # Should NOT be able to commit
        can_commit, reason = manager.can_commit(txn_id, 3)
        self.assertFalse(can_commit, f"Should not commit with NACK: {reason}")
        self.assertIn("NACK", reason)
    
    def test_timeout_treated_as_nack(self):
        """Test 8: Timeout votes prevent commit"""
        manager = CoordinatedCommitManager("node_1")
        
        success, msg, txn_id = manager.create_transaction(
            account_id=1,
            amount=Decimal(100),
            request_id="test_008",
            replica_ids=["node_1", "node_2", "node_3"]
        )
        
        # Record votes with timeout
        manager.record_prepare_vote(txn_id, "node_1", ReplicaVote.ACK)
        manager.record_prepare_vote(txn_id, "node_2", ReplicaVote.TIMEOUT)  # Timeout!
        manager.record_prepare_vote(txn_id, "node_3", ReplicaVote.ACK)
        
        # Should NOT be able to commit
        can_commit, reason = manager.can_commit(txn_id, 3)
        self.assertFalse(can_commit, f"Should not commit with TIMEOUT: {reason}")
        self.assertIn("timeout", reason.lower())
    
    def test_transaction_state_transitions(self):
        """Test 9: Transaction state properly transitions through phases"""
        manager = CoordinatedCommitManager("node_1")
        
        success, msg, txn_id = manager.create_transaction(
            account_id=1,
            amount=Decimal(100),
            request_id="test_009",
            replica_ids=["node_1", "node_2", "node_3"]
        )
        
        txn = manager.transactions[txn_id]
        
        # Initial state
        from src.core.coordinated_commit import CommitPhase
        self.assertEqual(txn.status, CommitPhase.PREPARE)
        
        # Move to COMMIT
        success, _ = manager.commit_transaction(txn_id)
        self.assertTrue(success)
        self.assertEqual(txn.status, CommitPhase.COMMIT)
        
        # Finalize
        success, _ = manager.finalize_transaction(txn_id)
        self.assertTrue(success)
    
    def test_consistency_across_all_replicas(self):
        """Test 10: Full end-to-end consistency check across all replicas"""
        # Perform multiple operations
        operations = [
            ("withdraw_1", Decimal(100)),
            ("withdraw_2", Decimal(200)),
            ("withdraw_3", Decimal(150)),
        ]
        
        node_1 = self.system.get_node('node_1')
        
        for request_id, amount in operations:
            success, _ = node_1.coordinated_withdraw(
                amount=amount,
                request_id=request_id
            )
            self.assertTrue(success)
        
        # Calculate expected final balance
        total_withdrawn = sum(amount for _, amount in operations)
        expected_balance = Decimal(1000) - total_withdrawn
        
        # Verify ALL replicas have exactly the same balance
        balances = {}
        for node_id, node in self.system.nodes.items():
            actual_balance = node.get_balance()
            balances[node_id] = actual_balance
            
            self.assertEqual(
                actual_balance, expected_balance,
                f"{node_id} has inconsistent balance: {actual_balance} vs {expected_balance}"
            )
        
        # All balances should be identical
        unique_balances = set(balances.values())
        self.assertEqual(len(unique_balances), 1, "Not all replicas have identical balance")
        print(f"\n✓ All replicas consistent: {balances}")


class TestEdgeCases(unittest.TestCase):
    """Edge case tests"""
    
    def setUp(self):
        self.system = DistributedSystem(account_id=2, num_nodes=3)
    
    def test_zero_amount_withdrawal(self):
        """Reject zero or negative withdrawals"""
        node_1 = self.system.get_node('node_1')
        
        success, message = node_1.coordinated_withdraw(
            amount=Decimal(0),
            request_id="edge_zero"
        )
        self.assertFalse(success)
    
    def test_withdrawal_equals_balance(self):
        """Withdrawal of entire balance should succeed"""
        node_1 = self.system.get_node('node_1')
        
        balance = node_1.get_balance()
        success, _ = node_1.coordinated_withdraw(
            amount=balance,
            request_id="edge_all"
        )
        self.assertTrue(success)
        
        # Verify all nodes at 0
        for node in self.system.nodes.values():
            self.assertEqual(node.get_balance(), Decimal(0))
    
    def test_withdrawal_exceeds_balance(self):
        """Withdrawal more than balance should fail"""
        node_1 = self.system.get_node('node_1')
        
        success, _ = node_1.coordinated_withdraw(
            amount=Decimal(10000),  # Much more than 1000
            request_id="edge_exceed"
        )
        self.assertFalse(success)
        
        # Balance should be unchanged
        self.assertEqual(node_1.get_balance(), Decimal(1000))


def run_tests():
    """Run all tests"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add tests
    suite.addTests(loader.loadTestsFromTestCase(Test2PCCoordinatedWithdrawal))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    
    # Run
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    print("\n" + "="*70)
    print("  TWO-PHASE COMMIT (2PC) TEST SUITE")
    print("="*70 + "\n")
    
    success = run_tests()
    
    print("\n" + "="*70)
    if success:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
    print("="*70 + "\n")
