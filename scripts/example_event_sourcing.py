"""
Integration example showing how to use the Event Sourcing + Checkpoint system
Demonstrates:
- System initialization
- Basic operations
- Event inspection
- System verification
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from decimal import Decimal

from src.core.distributed_system import DistributedSystem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def example_basic_usage():
    """Example: Basic deposit and withdrawal"""
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 1: BASIC DEPOSIT AND WITHDRAWAL")
    logger.info("=" * 70)
    
    # Create a 3-node distributed system
    system = DistributedSystem(account_id=1, num_nodes=3)
    
    print("\n[Initial State]")
    system.print_state()
    
    # Deposit $100 on node_1
    logger.info("Performing deposit on node_1...")
    success, msg = system.deposit("node_1", Decimal(100), request_id="dep_001")
    logger.info(f"Result: {msg}")
    
    print("\n[After Deposit on node_1]")
    system.print_state()
    
    # Now withdraw from node_2 (should sync deposits first)
    logger.info("\nPerforming withdrawal from node_2...")
    success, msg = system.withdraw("node_2", Decimal(50), request_id="wd_001")
    logger.info(f"Result: {msg}")
    
    print("\n[After Withdrawal from node_2]")
    system.print_state()
    
    # Verify system state
    converged, msg = system.verify_convergence()
    logger.info(f"\nConvergence check: {msg}")
    
    valid, msg = system.verify_no_double_spending()
    logger.info(f"Double spending check: {msg}")


def example_lazy_vs_strong_consistency():
    """Example: Demonstrate lazy propagation vs strong consistency"""
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 2: LAZY PROPAGATION vs STRONG CONSISTENCY")
    logger.info("=" * 70)
    
    system = DistributedSystem(account_id=1, num_nodes=2)
    
    print("\n[Initial State]")
    system.print_state()
    
    # Deposit on node_1 (lazy - not immediately visible on node_2)
    logger.info("\n--- LAZY PROPAGATION: Deposit on node_1 ---")
    system.deposit("node_1", Decimal(100), request_id="dep_101")
    
    logger.info(f"node_1 balance: {system.get_balance('node_1')}")
    logger.info(f"node_2 balance (before sync): {system.get_balance('node_2')}")
    
    # Withdrawal on node_2 triggers sync, making deposit visible
    logger.info("\n--- STRONG CONSISTENCY: Withdrawal on node_2 triggers sync ---")
    system.withdraw("node_2", Decimal(200), request_id="wd_101")
    
    logger.info(f"node_2 balance (after sync): {system.get_balance('node_2')}")
    
    print("\n[Final State - All Nodes Converged]")
    system.print_state()


def example_idempotency_and_retries():
    """Example: Demonstrate idempotency handles retries correctly"""
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 3: IDEMPOTENCY AND RETRIES")
    logger.info("=" * 70)
    
    system = DistributedSystem(account_id=1, num_nodes=1)
    
    logger.info("\nAttempt 1: First deposit with request_id='REQ_001'")
    success1, msg1 = system.deposit("node_1", Decimal(100), request_id="REQ_001")
    logger.info(f"Success: {success1}, Message: {msg1}")
    logger.info(f"Balance: {system.get_balance('node_1')}")
    
    logger.info("\nAttempt 2: RETRY with same request_id='REQ_001'")
    success2, msg2 = system.deposit("node_1", Decimal(100), request_id="REQ_001")
    logger.info(f"Success: {success2}, Message: {msg2}")
    logger.info(f"Balance: {system.get_balance('node_1')} (unchanged, duplicate rejected)")


def example_insufficient_balance():
    """Example: Demonstrate insufficient balance handling"""
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 4: INSUFFICIENT BALANCE HANDLING")
    logger.info("=" * 70)
    
    system = DistributedSystem(account_id=1, num_nodes=1)
    
    logger.info("\nStarting balance: 1000")
    logger.info("Attempting to withdraw: 2000")
    
    success, msg = system.withdraw("node_1", Decimal(2000), request_id="wd_999")
    logger.info(f"\nResult: {msg}")
    logger.info(f"Withdrawal was: {'APPROVED' if success else 'REJECTED'}")
    logger.info(f"Final balance: {system.get_balance('node_1')}")


def example_event_inspection():
    """Example: Inspect events and state"""
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 5: EVENT INSPECTION AND STATE INSPECTION")
    logger.info("=" * 70)
    
    system = DistributedSystem(account_id=1, num_nodes=2)
    
    # Perform operations
    system.deposit("node_1", Decimal(100), request_id="dep_001")
    system.deposit("node_1", Decimal(50), request_id="dep_002")
    system.withdraw("node_2", Decimal(75), request_id="wd_001")
    
    # Inspect node state
    logger.info("\n--- Node State Inspection ---")
    node1 = system.get_node("node_1")
    state = node1.get_state()
    
    logger.info(f"Node: {state['node_id']}")
    logger.info(f"Balance: {state['balance']}")
    logger.info(f"Events: {state['event_count']}")
    logger.info(f"Max Event ID: {state['max_event_id']}")
    logger.info(f"Checkpoint: last_event_id={state['checkpoint']['last_event_id']}, "
               f"balance={state['checkpoint']['balance']}")
    
    # Inspect events
    logger.info("\n--- Event Log Inspection (node_2) ---")
    node2 = system.get_node("node_2")
    events = node2.get_events()
    
    for event in events:
        logger.info(f"  Event {event['event_id']}: "
                   f"{event['type'].upper():8} ${event['amount']:>6} "
                   f"from {event['node_id']}")


def example_system_verification():
    """Example: Comprehensive system verification"""
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 6: COMPREHENSIVE SYSTEM VERIFICATION")
    logger.info("=" * 70)
    
    system = DistributedSystem(account_id=1, num_nodes=3)
    
    # Perform mixed operations
    operations = [
        ("node_1", "deposit", Decimal(200)),
        ("node_2", "deposit", Decimal(150)),
        ("node_3", "withdraw", Decimal(100)),
        ("node_1", "withdraw", Decimal(75)),
        ("node_2", "withdraw", Decimal(200)),
    ]
    
    for node_id, op_type, amount in operations:
        if op_type == "deposit":
            system.deposit(node_id, amount)
        else:
            system.withdraw(node_id, amount)
    
    print("\n[System State After Operations]")
    system.print_state()
    
    # Verification checks
    logger.info("\n--- VERIFICATION CHECKS ---")
    
    converged, msg = system.verify_convergence()
    status = "✓ PASS" if converged else "✗ FAIL"
    logger.info(f"{status}: Convergence - {msg}")
    
    valid, msg = system.verify_no_double_spending()
    status = "✓ PASS" if valid else "✗ FAIL"
    logger.info(f"{status}: No Double Spending - {msg}")
    
    balances = system.get_all_balances()
    all_positive = all(b >= 0 for b in balances.values())
    status = "✓ PASS" if all_positive else "✗ FAIL"
    logger.info(f"{status}: Non-Negative Balances")


def main():
    """Run all examples"""
    logger.info("\n" + "█" * 70)
    logger.info("█" + " " * 68 + "█")
    logger.info("█  DISTRIBUTED MOBILE MONEY SYSTEM - USAGE EXAMPLES".ljust(69) + "█")
    logger.info("█" + " " * 68 + "█")
    logger.info("█" * 70)
    
    example_basic_usage()
    example_lazy_vs_strong_consistency()
    example_idempotency_and_retries()
    example_insufficient_balance()
    example_event_inspection()
    example_system_verification()
    
    logger.info("\n" + "█" * 70)
    logger.info("█  ALL EXAMPLES COMPLETED".ljust(69) + "█")
    logger.info("█" * 70 + "\n")


if __name__ == "__main__":
    main()
