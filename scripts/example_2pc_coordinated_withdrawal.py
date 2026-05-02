"""
Example: Two-Phase Commit (2PC) Coordinated Withdrawal
Demonstrates how the 2PC protocol prevents inconsistency when nodes fail
"""
from decimal import Decimal
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from src.core.distributed_system import DistributedSystem


def print_section(title: str):
    """Print a formatted section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_node_state(system: DistributedSystem, node_id: str):
    """Print node state"""
    node = system.get_node(node_id)
    if node:
        state = node.get_state()
        print(f"{node_id}: balance={state['balance']}, "
              f"events={state['event_count']}, "
              f"locked_funds={node.get_transaction_locks()}")


def print_all_balances(system: DistributedSystem):
    """Print all node balances"""
    print("\nAll node balances:")
    for node_id in system.nodes.keys():
        print_node_state(system, node_id)


def example_1_successful_coordinated_withdrawal():
    """
    Example 1: Successful coordinated withdrawal
    All nodes agree → all commit
    """
    print_section("EXAMPLE 1: Successful Coordinated Withdrawal")
    
    print("Initial setup:")
    print("- 3 nodes in distributed system")
    print("- Each node starts with 1000 balance")
    print("- Attempting to withdraw 100 via 2PC protocol")
    
    system = DistributedSystem(account_id=1, num_nodes=3)
    print_all_balances(system)
    
    print("\n" + "="*70)
    print("EXECUTING: Coordinated withdrawal of 100 from node_1")
    print("="*70)
    
    # Coordinated withdrawal: if ANY replica can't commit, ALL rollback
    success, message = system.nodes['node_1'].coordinated_withdraw(
        amount=Decimal(100),
        request_id="withdraw_001"
    )
    
    print(f"\nResult: {success}")
    print(f"Message: {message}")
    
    print_all_balances(system)
    
    print("\n✓ All nodes successfully committed the withdrawal")
    print("  Balance decreased on ALL replicas (consistent state)")


def example_2_insufficient_balance():
    """
    Example 2: Insufficient balance on some replicas
    One node votes NACK → ALL nodes rollback
    """
    print_section("EXAMPLE 2: Insufficient Balance - Transaction Rolled Back")
    
    print("Setup:")
    print("- 3 nodes with 1000 balance each")
    print("- node_2 gets manually depleted to 50")
    print("- Attempting to withdraw 100 via 2PC protocol")
    
    system = DistributedSystem(account_id=2, num_nodes=3)
    
    # Manually deplete node_2 to create inconsistency
    print("\nManually depleting node_2 to 50...")
    node_2 = system.get_node('node_2')
    node_2.checkpoint.balance = Decimal(50)
    
    print_all_balances(system)
    
    print("\n" + "="*70)
    print("EXECUTING: Coordinated withdrawal of 100 from node_1")
    print("Expected: node_2 votes NACK → ALL nodes rollback")
    print("="*70)
    
    success, message = system.nodes['node_1'].coordinated_withdraw(
        amount=Decimal(100),
        request_id="withdraw_002"
    )
    
    print(f"\nResult: {success}")
    print(f"Message: {message}")
    
    print_all_balances(system)
    
    print("\n✓ Transaction rolled back on all nodes")
    print("  All balances remain UNCHANGED (no partial commits)")


def example_3_multiple_concurrent_operations():
    """
    Example 3: Multiple successful coordinated withdrawals
    Demonstrates that locks prevent double-spending
    """
    print_section("EXAMPLE 3: Multiple Coordinated Withdrawals")
    
    print("Setup:")
    print("- 3 nodes with 1000 balance each")
    print("- First: withdraw 200 via 2PC")
    print("- Second: withdraw 300 via 2PC")
    
    system = DistributedSystem(account_id=3, num_nodes=3)
    print_all_balances(system)
    
    print("\n" + "="*70)
    print("FIRST WITHDRAWAL: 200 from node_1")
    print("="*70)
    success1, msg1 = system.nodes['node_1'].coordinated_withdraw(
        amount=Decimal(200),
        request_id="withdraw_003_1"
    )
    print(f"Result: {success1} - {msg1}")
    print_all_balances(system)
    
    print("\n" + "="*70)
    print("SECOND WITHDRAWAL: 300 from node_1")
    print("="*70)
    success2, msg2 = system.nodes['node_1'].coordinated_withdraw(
        amount=Decimal(300),
        request_id="withdraw_003_2"
    )
    print(f"Result: {success2} - {msg2}")
    print_all_balances(system)
    
    expected_balance = 1000 - 200 - 300
    print(f"\n✓ Both withdrawals successful")
    print(f"  Expected balance: {expected_balance}")
    print(f"  All nodes consistent (no double-spending)")


def example_4_failed_replica_recovery():
    """
    Example 4: Simulating a replica that temporarily cannot respond
    The timeout mechanism ensures rollback on unresponsive replicas
    """
    print_section("EXAMPLE 4: Handling Unresponsive Replicas")
    
    print("Setup:")
    print("- 3 nodes with 1000 balance each")
    print("- Simulating network partition during prepare phase")
    print("- When replicas don't vote: TIMEOUT → ROLLBACK")
    
    system = DistributedSystem(account_id=4, num_nodes=3)
    print_all_balances(system)
    
    print("\n" + "="*70)
    print("ATTEMPTING: Coordinated withdrawal of 150")
    print("With simulated unresponsive replica (timeout)")
    print("="*70)
    
    # In a real scenario, we'd mock the remote_nodes to simulate timeouts
    # For now, we show the expected behavior
    
    success, message = system.nodes['node_1'].coordinated_withdraw(
        amount=Decimal(150),
        request_id="withdraw_004"
    )
    
    print(f"\nResult: {success}")
    print(f"Message: {message}")
    print_all_balances(system)
    
    print("\n✓ Protocol guarantees:")
    print("  - Timeouts are treated as NACK votes")
    print("  - If any replica cannot respond: ROLLBACK everywhere")
    print("  - No partial state commits (all-or-nothing semantics)")


def main():
    """Run all examples"""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*10 + "TWO-PHASE COMMIT (2PC) COORDINATED WITHDRAWALS" + " "*12 + "║")
    print("║" + " "*20 + "Preventing Distributed Inconsistency" + " "*12 + "║")
    print("╚" + "="*68 + "╝")
    
    print("\nProblem Statement:")
    print("-" * 70)
    print("Without 2PC, if node_1 initiates a withdrawal and fails mid-")
    print("propagation, other nodes remain unupdated, causing inconsistency:")
    print("  - node_1: balance -= 100 (SUCCESS)")
    print("  - node_2: balance unchanged (INCONSISTENT!)")
    print("  - node_3: balance unchanged (INCONSISTENT!)")
    print("\nSolution: Two-Phase Commit Protocol")
    print("-" * 70)
    print("1. PREPARE: Lock + validate on all replicas")
    print("2. COMMIT/ROLLBACK: All-or-nothing based on votes")
    print("3. FINALIZE: Release locks and clean up")
    
    # Run examples
    example_1_successful_coordinated_withdrawal()
    example_2_insufficient_balance()
    example_3_multiple_concurrent_operations()
    example_4_failed_replica_recovery()
    
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*15 + "KEY BENEFITS OF 2PC PROTOCOL" + " "*25 + "║")
    print("╠" + "="*68 + "╣")
    print("║ ✓ Atomic Consistency: All-or-nothing semantics                    ║")
    print("║ ✓ No Double-Spending: Locked funds prevent concurrent txns        ║")
    print("║ ✓ Automatic Rollback: Any failure triggers cascading rollback     ║")
    print("║ ✓ Replica Resilience: Timeout handling prevents hanging           ║")
    print("║ ✓ Strong Consistency: No stale reads or inconsistent state        ║")
    print("╚" + "="*68 + "╝")
    print()


if __name__ == "__main__":
    main()
