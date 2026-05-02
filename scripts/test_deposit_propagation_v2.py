"""
Test lazy vs instant propagation for deposits and withdrawals - FIXED VERSION
Verifies if deposits are lazy and how they propagate on balance check
"""
import sys
from pathlib import Path
from decimal import Decimal

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.distributed_system import DistributedSystem
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def print_section(title):
    """Print section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def test_scenario_1_deposit_lazy_no_balance_call():
    """
    Test: Verify deposits are NOT propagated when we DON'T read balance
    Expected: node_2 event_log stays empty until we explicitly sync
    """
    print_section("TEST 1: DEPOSIT LAZY (No balance call)")
    
    # Create 3-node system
    system = DistributedSystem(account_id=1, num_nodes=3)
    
    print(">>> Step 1: Initial state")
    print(f"  node_1 event count: {len(system.nodes['node_1'].event_log.get_all_events())}")
    print(f"  node_2 event count: {len(system.nodes['node_2'].event_log.get_all_events())}")
    print(f"  node_3 event count: {len(system.nodes['node_3'].event_log.get_all_events())}")
    
    print("\n>>> Step 2: node_1 deposits 100")
    success, msg = system.nodes['node_1'].deposit(Decimal(100), request_id="deposit_001")
    print(f"  Deposit result: {success}")
    print(f"  node_1 event count: {len(system.nodes['node_1'].event_log.get_all_events())}")
    print(f"  node_2 event count: {len(system.nodes['node_2'].event_log.get_all_events())}")
    print(f"  node_3 event count: {len(system.nodes['node_3'].event_log.get_all_events())}")
    
    # KEY TEST: Check if deposit is in node_2's event_log WITHOUT calling get_balance
    print("\n>>> KEY TEST: Check node_2 event_log WITHOUT calling get_balance()")
    node2_events = system.nodes['node_2'].event_log.get_all_events()
    print(f"  node_2 events in event_log: {len(node2_events)}")
    
    if len(node2_events) == 0:
        print("  [PASS] Deposit NOT in node_2 event_log (lazy works!)")
        return True
    else:
        print("  [FAIL] Deposit IS in node_2 event_log (not lazy)")
        return False

def test_scenario_2_deposit_on_demand_sync():
    """
    Test: Verify deposits ARE synced when we read balance (on-demand)
    Expected: node_2 gets deposit event when we call get_balance()
    """
    print_section("TEST 2: DEPOSIT ON-DEMAND (Balance call triggers sync)")
    
    system = DistributedSystem(account_id=1, num_nodes=3)
    
    print(">>> Step 1: node_1 deposits 100")
    system.nodes['node_1'].deposit(Decimal(100), request_id="deposit_001")
    print(f"  node_1 event count: {len(system.nodes['node_1'].event_log.get_all_events())}")
    print(f"  node_2 event count (before balance call): {len(system.nodes['node_2'].event_log.get_all_events())}")
    
    print("\n>>> Step 2: node_2 calls get_balance() (triggers sync)")
    balance = system.nodes['node_2'].get_balance()
    print(f"  node_2 balance: {balance} (expected: 1100)")
    print(f"  node_2 event count (after balance call): {len(system.nodes['node_2'].event_log.get_all_events())}")
    
    # Check result
    node2_has_deposit = any(
        evt.type.value == 'deposit' 
        for evt in system.nodes['node_2'].event_log.get_all_events()
    )
    
    print("\n>>> KEY TEST: Did on-demand sync work?")
    if balance == Decimal(1100) and node2_has_deposit:
        print("  [PASS] Balance synced and shows 1100 (on-demand works!)")
        return True
    else:
        print(f"  [FAIL] Balance: {balance}, events: {len(system.nodes['node_2'].event_log.get_all_events())}")
        return False

def test_scenario_3_withdrawal_instant():
    """
    Test: Verify withdrawals ARE instantly propagated
    Expected: node_2 gets withdrawal event immediately without sync call
    """
    print_section("TEST 3: WITHDRAWAL INSTANT PROPAGATION")
    
    system = DistributedSystem(account_id=1, num_nodes=3)
    
    # Setup: all nodes at 1100 via sync
    print(">>> Setup: Deposit and sync")
    system.nodes['node_1'].deposit(Decimal(100), request_id="dep_setup")
    _ = system.nodes['node_2'].get_balance()  # Trigger sync
    _ = system.nodes['node_3'].get_balance()  # Trigger sync
    
    print(f"  node_1 events: {len(system.nodes['node_1'].event_log.get_all_events())}")
    print(f"  node_2 events: {len(system.nodes['node_2'].event_log.get_all_events())}")
    print(f"  node_3 events: {len(system.nodes['node_3'].event_log.get_all_events())}")
    
    print("\n>>> Step 1: node_1 withdraws 50")
    withdrawal_count_before = len(system.nodes['node_2'].event_log.get_all_events())
    system.nodes['node_1'].withdraw(Decimal(50), request_id="wd_001")
    withdrawal_count_after = len(system.nodes['node_2'].event_log.get_all_events())
    
    print(f"  node_1 events: {len(system.nodes['node_1'].event_log.get_all_events())}")
    print(f"  node_2 events before: {withdrawal_count_before}, after: {withdrawal_count_after}")
    
    # Check if node_2 got the withdrawal immediately
    node2_has_withdrawal = any(
        evt.type.value == 'withdraw' 
        for evt in system.nodes['node_2'].event_log.get_all_events()
    )
    
    print("\n>>> KEY TEST: Instant withdrawal propagation?")
    if node2_has_withdrawal and withdrawal_count_after > withdrawal_count_before:
        print("  [PASS] Withdrawal was instantly propagated to node_2!")
        return True
    else:
        print("  [FAIL] Withdrawal NOT instantly propagated")
        return False

def test_scenario_4_consistency_check():
    """
    Test: Verify all nodes converge to same balance
    """
    print_section("TEST 4: CONSISTENCY CHECK")
    
    system = DistributedSystem(account_id=1, num_nodes=3)
    
    print(">>> Operations:")
    print("  1. node_1 deposits 100")
    system.nodes['node_1'].deposit(Decimal(100), request_id="dep_1")
    
    print("  2. node_2 deposits 50")
    system.nodes['node_2'].deposit(Decimal(50), request_id="dep_2")
    
    print("  3. node_3 withdraws 30")
    system.nodes['node_3'].withdraw(Decimal(30), request_id="wd_1")
    
    print("\n>>> Final balances (after reading):")
    b1 = system.nodes['node_1'].get_balance()
    b2 = system.nodes['node_2'].get_balance()
    b3 = system.nodes['node_3'].get_balance()
    
    print(f"  node_1 balance: {b1}")
    print(f"  node_2 balance: {b2}")
    print(f"  node_3 balance: {b3}")
    print(f"  Expected: 1120 (1000 + 100 + 50 - 30)")
    
    if b1 == b2 == b3 == Decimal(1120):
        print("  [PASS] All nodes converged to same balance!")
        return True
    else:
        print("  [FAIL] Nodes have different balances")
        return False

def print_results(results):
    """Print test results"""
    print_section("TEST RESULTS SUMMARY")
    
    tests = [
        ("Test 1: Lazy Deposit (no balance call)", results[0]),
        ("Test 2: On-Demand Sync (balance call)", results[1]),
        ("Test 3: Instant Withdrawal", results[2]),
        ("Test 4: Consistency", results[3]),
    ]
    
    passed = 0
    for name, result in tests:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")
        if result:
            passed += 1
    
    print(f"\n  Total: {passed}/{len(tests)} tests passed")
    return passed == len(tests)

if __name__ == "__main__":
    try:
        print("\n" + "="*70)
        print("  LAZY PROPAGATION VERIFICATION TEST")
        print("="*70)
        
        results = [
            test_scenario_1_deposit_lazy_no_balance_call(),
            test_scenario_2_deposit_on_demand_sync(),
            test_scenario_3_withdrawal_instant(),
            test_scenario_4_consistency_check(),
        ]
        
        all_pass = print_results(results)
        
        if all_pass:
            print("\n[SUCCESS] All tests passed!")
            print("\nSystem behavior:")
            print("  - Deposits: Lazy (not propagated until balance read)")
            print("  - Withdrawals: Instant (propagated immediately)")
            print("  - Balance reads: Trigger on-demand sync")
            print("  - Consistency: Eventual consistency achieved")
            sys.exit(0)
        else:
            print("\n[FAILURE] Some tests failed")
            sys.exit(1)
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
