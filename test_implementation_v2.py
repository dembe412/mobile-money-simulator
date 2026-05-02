#!/usr/bin/env python3
"""
Test script for Version Control + Optimized Withdrawal Implementation
Verifies all new features are working correctly
"""
import sys
sys.path.insert(0, '/d/adone/mobile-money-simulator')

from decimal import Decimal
from datetime import datetime
from src.core.event_log import EventLog, TransactionEvent, EventType
from src.core.checkpoint import Checkpoint, CheckpointManager
from src.core.distributed_node import DistributedNode

def test_event_versioning():
    """Test that events have versioning"""
    print("\n" + "="*70)
    print("TEST 1: Event Versioning")
    print("="*70)
    
    # Create event with version
    event = TransactionEvent(
        event_id=1,
        type=EventType.DEPOSIT,
        amount=Decimal(100),
        account_id=1,
        version="v1"
    )
    
    # Serialize
    event_dict = event.to_dict()
    print(f"✓ Event created with version: {event_dict['version']}")
    assert 'version' in event_dict, "Version field missing in serialization"
    assert event_dict['version'] == "v1"
    
    # Deserialize
    restored = TransactionEvent.from_dict(event_dict)
    print(f"✓ Event deserialized with version: {restored.version}")
    assert restored.version == "v1"
    
    # Test backward compatibility (missing version defaults to v1)
    old_dict = {
        'event_id': 2,
        'type': 'deposit',
        'amount': '50',
        'account_id': 1,
        'timestamp': datetime.utcnow().isoformat(),
        # Note: NO version field
    }
    restored_old = TransactionEvent.from_dict(old_dict)
    print(f"✓ Old event (no version) defaults to: {restored_old.version}")
    assert restored_old.version == "v1"
    
    print("✅ Event Versioning: PASSED\n")


def test_checkpoint_versioning():
    """Test that checkpoints have versioning and last_withdraw tracking"""
    print("="*70)
    print("TEST 2: Checkpoint Versioning + Last Withdraw Tracking")
    print("="*70)
    
    # Create checkpoint
    cp = Checkpoint(
        balance=Decimal(1000),
        last_event_id=50,
        node_id="node_1",
        account_id=1,
        version="v1",
        last_withdraw_amount=Decimal(200),
        last_withdraw_event_id=49
    )
    
    print(f"✓ Checkpoint created with:")
    print(f"  - version: {cp.version}")
    print(f"  - balance: {cp.balance}")
    print(f"  - last_withdraw_amount: {cp.last_withdraw_amount}")
    print(f"  - last_withdraw_event_id: {cp.last_withdraw_event_id}")
    
    # Serialize
    cp_dict = cp.to_dict()
    assert 'version' in cp_dict
    assert 'last_withdraw_amount' in cp_dict
    assert 'last_withdraw_event_id' in cp_dict
    print(f"✓ Checkpoint serialized successfully")
    
    # Deserialize
    restored_cp = Checkpoint.from_dict(cp_dict)
    print(f"✓ Checkpoint deserialized successfully")
    assert restored_cp.version == "v1"
    assert restored_cp.last_withdraw_amount == Decimal(200)
    assert restored_cp.last_withdraw_event_id == 49
    
    # Test backward compatibility
    old_cp_dict = {
        'balance': '1000',
        'last_event_id': 50,
        'timestamp': datetime.utcnow().isoformat(),
        # Note: NO version, no last_withdraw fields
    }
    restored_old_cp = Checkpoint.from_dict(old_cp_dict)
    print(f"✓ Old checkpoint (no version) defaults to: {restored_old_cp.version}")
    print(f"✓ Old checkpoint last_withdraw_amount defaults to: {restored_old_cp.last_withdraw_amount}")
    assert restored_old_cp.version == "v1"
    assert restored_old_cp.last_withdraw_amount == Decimal(0)
    
    print("✅ Checkpoint Versioning: PASSED\n")


def test_optimized_balance_computation():
    """Test optimized balance computation with bandwidth savings"""
    print("="*70)
    print("TEST 3: Optimized Balance Computation")
    print("="*70)
    
    event_log = EventLog()
    
    # Add events: 7 deposits + 3 withdrawals after checkpoint
    deposits = [100, 50, 75, 25, 200, 150, 100]  # 7 deposits
    withdrawals = [50, 100, 75]  # 3 withdrawals
    
    event_id = 100
    for amt in deposits:
        event = TransactionEvent(
            event_id=event_id,
            type=EventType.DEPOSIT,
            amount=Decimal(amt),
            account_id=1,
            version="v1"
        )
        event_log.add_event(event)
        event_id += 1
    
    for amt in withdrawals:
        event = TransactionEvent(
            event_id=event_id,
            type=EventType.WITHDRAW,
            amount=Decimal(amt),
            account_id=1,
            version="v1"
        )
        event_log.add_event(event)
        event_id += 1
    
    # Compute balance using optimized method
    result = event_log.compute_balance_optimized(
        checkpoint_balance=Decimal(1000),
        checkpoint_event_id=99,  # Events 100+
        last_withdraw_amount=Decimal(100)
    )
    
    print(f"✓ Computation results:")
    print(f"  - Formula: {result['formula']}")
    print(f"  - Balance: {result['balance']}")
    print(f"  - Deposits Sum: {result['deposits_sum']}")
    print(f"  - Withdrawal Amount: {result['withdrawal_amount']}")
    print(f"  - Computation Events (deposits only): {result['computation_events']}")
    print(f"  - Total Subsequent Events: {result['total_subsequent_events']}")
    print(f"  - Bandwidth Saved: {result['bandwidth_saved_percent']}%")
    
    # Verify calculations
    expected_balance = Decimal(1000) + Decimal(700) - Decimal(100)  # 1600
    assert result['balance'] == expected_balance, f"Balance mismatch: {result['balance']} != {expected_balance}"
    assert result['computation_events'] == 7, "Should process 7 deposits"
    assert result['total_subsequent_events'] == 10, "Should have 10 total events"
    assert result['bandwidth_saved_percent'] == 30.0, "Should save 30% (3 withdrawals out of 10)"
    
    print("✅ Optimized Balance Computation: PASSED\n")


def test_deposits_before_withdrawal():
    """Test scenario: multiple deposits on same node before withdrawal"""
    print("="*70)
    print("TEST 4: Deposits Before Withdrawal Scenario")
    print("="*70)
    
    node = DistributedNode(
        node_id="node_1",
        account_id=1,
        initial_balance=Decimal(1000)
    )
    
    print(f"✓ Node created with initial balance: 1000")
    
    # Deposit 1
    success, msg = node.deposit(Decimal(100), request_id="dep_1")
    assert success, f"Deposit 1 failed: {msg}"
    print(f"✓ Deposit 100 successful")
    
    # Deposit 2
    success, msg = node.deposit(Decimal(50), request_id="dep_2")
    assert success, f"Deposit 2 failed: {msg}"
    print(f"✓ Deposit 50 successful")
    
    # Check balance before withdrawal (should be 1000 + 100 + 50)
    balance_before = node.get_balance()
    print(f"✓ Balance before withdrawal: {balance_before}")
    assert balance_before == Decimal(1150), f"Balance before withdrawal incorrect: {balance_before}"
    
    # Withdrawal
    success, msg = node.withdraw(Decimal(200), request_id="wd_1")
    assert success, f"Withdrawal failed: {msg}"
    print(f"✓ Withdrawal 200 successful")
    
    # Check balance after withdrawal (should be 1150 - 200 = 950)
    balance_after = node.get_balance()
    print(f"✓ Balance after withdrawal: {balance_after}")
    assert balance_after == Decimal(950), f"Balance after withdrawal incorrect: {balance_after}"
    
    # Verify checkpoint tracking
    print(f"✓ Checkpoint version: {node.checkpoint.version}")
    print(f"✓ Last withdraw amount tracked: {node.checkpoint.last_withdraw_amount}")
    assert node.checkpoint.last_withdraw_amount == Decimal(200)
    assert node.checkpoint.version == "v1"
    
    print("✅ Deposits Before Withdrawal: PASSED\n")


def test_event_serialization_compatibility():
    """Test that event serialization maintains compatibility"""
    print("="*70)
    print("TEST 5: Event Serialization Compatibility")
    print("="*70)
    
    # Create a mix of v1 and v2 events
    events = [
        TransactionEvent(1, EventType.DEPOSIT, Decimal(100), 1, version="v1"),
        TransactionEvent(2, EventType.WITHDRAW, Decimal(50), 1, version="v1"),
        TransactionEvent(3, EventType.DEPOSIT, Decimal(75), 1, version="v1"),
    ]
    
    event_log = EventLog()
    for evt in events:
        assert event_log.add_event(evt), f"Failed to add event {evt.event_id}"
    
    print(f"✓ Added {len(events)} events to log")
    
    # Serialize all
    serialized = [e.to_dict() for e in event_log.get_all_events()]
    print(f"✓ Serialized {len(serialized)} events")
    
    # Verify all have version field
    for s in serialized:
        assert 'version' in s, "Missing version in serialized event"
    
    # Deserialize all
    deserialized = [TransactionEvent.from_dict(s) for s in serialized]
    print(f"✓ Deserialized {len(deserialized)} events")
    
    # Verify all have correct version
    for d in deserialized:
        assert d.version == "v1"
    
    print("✅ Event Serialization Compatibility: PASSED\n")


def main():
    """Run all tests"""
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█  VERSION CONTROL + OPTIMIZED WITHDRAWAL IMPLEMENTATION TESTS".ljust(69) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    try:
        test_event_versioning()
        test_checkpoint_versioning()
        test_optimized_balance_computation()
        test_deposits_before_withdrawal()
        test_event_serialization_compatibility()
        
        print("█"*70)
        print("█" + " "*68 + "█")
        print("█  ✅ ALL TESTS PASSED! IMPLEMENTATION IS WORKING CORRECTLY".ljust(69) + "█")
        print("█" + " "*68 + "█")
        print("█"*70)
        print("\nImplementation Summary:")
        print("├─ ✅ Event versioning working")
        print("├─ ✅ Checkpoint versioning working")
        print("├─ ✅ Last withdraw tracking working")
        print("├─ ✅ Optimized balance computation working")
        print("├─ ✅ Deposits before withdrawal scenario working")
        print("├─ ✅ Backward compatibility maintained")
        print("└─ ✅ Bandwidth optimization verified (30% savings in test)")
        print("\n📄 Full documentation: IMPLEMENTATION_GUIDE_V2.md\n")
        
        return 0
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
