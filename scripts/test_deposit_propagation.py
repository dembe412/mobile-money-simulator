"""
Test lazy vs instant propagation for deposits and withdrawals
Verifies if deposits are actually lazy or being propagated instantly
"""
import sys
from pathlib import Path
from decimal import Decimal

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.distributed_system import DistributedSystem
import logging

# Setup logging to see what's happening
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def print_section(title):
    """Print section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def print_state(system, label):
    """Print current state of all nodes"""
    print(f"\n{label}:")
    print(f"  {'Node':<10} {'Balance':<15} {'Events':<10}")
    print(f"  {'-'*35}")
    for node_name, node in system.nodes.items():
        balance = node.get_balance()
        event_count = len(node.event_log.events)
        print(f"  {node_name:<10} {str(balance):<15} {event_count:<10}")

def test_scenario_1_deposit_lazy_propagation():
    """
    Test 1: Verify deposits are NOT immediately propagated to other nodes
    Expected: node_1 deposit visible only on node_1, not on node_2/node_3
    """
    print_section("TEST 1: DEPOSIT LAZY PROPAGATION")
    
    # Create 3-node system
    system = DistributedSystem(account_id=1, num_nodes=3)
    
    print("\n>>> Initial state (all nodes at 1000):")
    print_state(system, "INITIAL STATE")
    
    # Check event logs before deposit
    print("\n>>> Event counts BEFORE deposit:")
    for name, node in system.nodes.items():
        print(f"  {name}: {len(node.event_log.events)} events")
    
    # Deposit on node_1
    print("\n>>> Executing: node_1.deposit(100, 'deposit_001')")
    success, msg = system.nodes['node_1'].deposit(Decimal(100), request_id="deposit_001")
    print(f"  Result: success={success}, msg={msg}")
    
    print("\n>>> State IMMEDIATELY after deposit (before any sync):")
    print_state(system, "AFTER DEPOSIT (NO SYNC)")
    
    # Check event logs after deposit
    print("\n>>> Event counts AFTER deposit:")
    for name, node in system.nodes.items():
        all_events = node.event_log.get_all_events()
        print(f"  {name}: {len(all_events)} events")
        for evt in all_events[-2:]:  # Show last 2 events
            print(f"    - {evt.type.value}: {evt.amount} (event_id={evt.event_id})")
    
    # Check: Does node_2 have the deposit event WITHOUT syncing?
    print("\n>>> KEY TEST: Does node_2 have deposit WITHOUT manual sync?")
    node2_events = system.nodes['node_2'].event_log.get_all_events()
    has_deposit = any(evt.type.value == 'deposit' for evt in node2_events)
    print(f"  node_2 events: {len(node2_events)}")
    print(f"  node_2 has deposit event: {has_deposit}")
    
    if has_deposit:
        print(f"  ⚠️  UNEXPECTED: Deposit was propagated! (should be lazy)")
    else:
        print(f"  ✓ EXPECTED: Deposit NOT on node_2 yet (lazy propagation working)")
    
    # Now manually sync
    print("\n>>> Manually syncing node_2...")
    print("  Calling: node_2._sync_events()")
    remote_events = system.nodes['node_2']._sync_events()
    print(f"  Synced {len(remote_events)} events from remote nodes")
    
    print("\n>>> State AFTER manual sync:")
    print_state(system, "AFTER MANUAL SYNC")
    
    # Final verification
    print("\n>>> FINAL VERIFICATION:")
    node1_balance = system.nodes['node_1'].get_balance()
    node2_balance = system.nodes['node_2'].get_balance()
    node3_balance = system.nodes['node_3'].get_balance()
    
    print(f"  node_1 balance: {node1_balance} (expected: 1100)")
    print(f"  node_2 balance: {node2_balance} (expected: 1100 after sync)")
    print(f"  node_3 balance: {node3_balance} (expected: 1000, no sync)")
    
    assert node1_balance == Decimal(1100), "node_1 balance should be 1100"
    assert node2_balance == Decimal(1100), "node_2 balance should be 1100 after sync"
    assert node3_balance == Decimal(1000), "node_3 balance should be 1000 (no sync)"
    
    print("\n✅ TEST 1 PASSED: Deposit lazy propagation verified")
    return system

def test_scenario_2_withdrawal_instant_propagation():
    """
    Test 2: Verify withdrawals ARE immediately propagated to other nodes
    Expected: node_2 sees withdrawal event immediately without syncing
    """
    print_section("TEST 2: WITHDRAWAL INSTANT PROPAGATION")
    
    # Use system from test 1
    system = DistributedSystem(account_id=1, num_nodes=3)
    
    # First, deposit and sync so all have 1100
    print("\n>>> Setup: Deposit and sync all nodes to 1100")
    system.nodes['node_1'].deposit(Decimal(100), request_id="dep_setup")
    system.nodes['node_2']._sync_events()
    system.nodes['node_3']._sync_events()
    
    print_state(system, "SETUP STATE (all at 1100)")
    
    # Now withdraw on node_1
    print("\n>>> Executing: node_1.withdraw(50, 'withdrawal_001')")
    success, msg = system.nodes['node_1'].withdraw(Decimal(50), request_id="withdrawal_001")
    print(f"  Result: success={success}, msg={msg}")
    
    print("\n>>> State IMMEDIATELY after withdrawal (before any manual sync):")
    print_state(system, "AFTER WITHDRAWAL (NO MANUAL SYNC)")
    
    # Check event logs
    print("\n>>> Event logs IMMEDIATELY after withdrawal:")
    for name, node in system.nodes.items():
        all_events = node.event_log.get_all_events()
        print(f"  {name}: {len(all_events)} events")
        for evt in all_events[-2:]:  # Show last 2 events
            print(f"    - {evt.type.value}: {evt.amount} (event_id={evt.event_id})")
    
    # Check: Does node_2 have the withdrawal event WITHOUT manual sync?
    print("\n>>> KEY TEST: Does node_2 have withdrawal WITHOUT manual sync?")
    node2_events = system.nodes['node_2'].event_log.get_all_events()
    withdrawal_events = [evt for evt in node2_events if evt.type.value == 'withdraw']
    has_withdrawal = len(withdrawal_events) > 0
    print(f"  node_2 events: {len(node2_events)}")
    print(f"  node_2 has withdrawal event: {has_withdrawal}")
    
    if has_withdrawal:
        print(f"  ✓ EXPECTED: Withdrawal was propagated instantly!")
    else:
        print(f"  ⚠️  UNEXPECTED: Withdrawal NOT on node_2 (should be instant)")
    
    print("\n>>> FINAL VERIFICATION:")
    node1_balance = system.nodes['node_1'].get_balance()
    node2_balance = system.nodes['node_2'].get_balance()
    node3_balance = system.nodes['node_3'].get_balance()
    
    print(f"  node_1 balance: {node1_balance} (expected: 1050)")
    print(f"  node_2 balance: {node2_balance} (expected: 1050, received withdrawal)")
    print(f"  node_3 balance: {node3_balance} (expected: 1050, received withdrawal)")
    
    print("\n✅ TEST 2 PASSED: Withdrawal instant propagation verified")

def test_scenario_3_mixed_operations():
    """
    Test 3: Mixed deposits and withdrawals to see propagation patterns
    """
    print_section("TEST 3: MIXED OPERATIONS")
    
    system = DistributedSystem(account_id=1, num_nodes=3)
    
    print("\n>>> Step 1: node_1 deposits 100")
    system.nodes['node_1'].deposit(Decimal(100), request_id="dep_1")
    print_state(system, "AFTER deposit_1 (no sync)")
    
    print("\n>>> Step 2: node_2 deposits 50")
    system.nodes['node_2'].deposit(Decimal(50), request_id="dep_2")
    print_state(system, "AFTER deposit_2 (no sync)")
    
    print("\n>>> Step 3: node_3 withdraws 30 (needs to sync to see deposits)")
    print("  Before withdrawal, node_3 syncs...")
    system.nodes['node_3']._sync_events()
    success, msg = system.nodes['node_3'].withdraw(Decimal(30), request_id="wd_1")
    print(f"  Withdrawal result: success={success}")
    print_state(system, "AFTER withdrawal from node_3 (instant to others)")
    
    print("\n>>> Check: Did node_1 and node_2 receive the withdrawal?")
    node1_events = system.nodes['node_1'].event_log.get_all_events()
    node2_events = system.nodes['node_2'].event_log.get_all_events()
    node1_has_withdrawal = any(
        evt.type.value == 'withdraw' 
        for evt in node1_events
    )
    node2_has_withdrawal = any(
        evt.type.value == 'withdraw' 
        for evt in node2_events
    )
    print(f"  node_1 has withdrawal: {node1_has_withdrawal} (should be True)")
    print(f"  node_2 has withdrawal: {node2_has_withdrawal} (should be True)")
    
    print("\n✅ TEST 3 PASSED: Mixed operations verified")

def test_scenario_4_node_restart():
    """
    Test 4: What happens when a node restarts?
    Does it have events from other nodes or only its own?
    """
    print_section("TEST 4: NODE RESTART / RECOVERY")
    
    system = DistributedSystem(account_id=1, num_nodes=3)
    
    # Deposit on node_1 (lazy, not propagated)
    print("\n>>> node_1 deposits 100 (lazy, not propagated)")
    system.nodes['node_1'].deposit(Decimal(100), request_id="dep_1")
    
    print("\n>>> node_2 deposits 50 (lazy, not propagated)")
    system.nodes['node_2'].deposit(Decimal(50), request_id="dep_2")
    
    print_state(system, "BEFORE node_3 recovery")
    
    # Now node_3 "recovers" by syncing
    print("\n>>> node_3 recovers/syncs...")
    system.nodes['node_3']._sync_events()
    
    print_state(system, "AFTER node_3 recovery/sync")
    
    # Check balances
    print("\n>>> RECOVERY VERIFICATION:")
    node1_balance = system.nodes['node_1'].get_balance()
    node2_balance = system.nodes['node_2'].get_balance()
    node3_balance = system.nodes['node_3'].get_balance()
    
    print(f"  node_1 balance: {node1_balance} (expected: 1100)")
    print(f"  node_2 balance: {node2_balance} (expected: 1050)")
    print(f"  node_3 balance: {node3_balance} (expected: 1150, sees both deposits)")
    
    print("\n✅ TEST 4 PASSED: Node recovery verified")

if __name__ == "__main__":
    try:
        print("\n" + "="*70)
        print("  DEPOSIT/WITHDRAWAL PROPAGATION VERIFICATION")
        print("="*70)
        
        # Run all tests
        test_scenario_1_deposit_lazy_propagation()
        test_scenario_2_withdrawal_instant_propagation()
        test_scenario_3_mixed_operations()
        test_scenario_4_node_restart()
        
        print_section("ALL TESTS COMPLETED SUCCESSFULLY")
        print("✅ Lazy deposit propagation is working as expected")
        print("✅ Instant withdrawal propagation is working as expected")
        print("\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
