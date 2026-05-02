# Lazy Propagation Bug Analysis

## The Problem Found

### Current Flow (BROKEN):
```
node_1 deposits 100 (lazy, not propagated to node_2)
  node_1.event_log: [DepositEvent(100)]  ✓
  node_2.event_log: []  ← Empty!

node_2.get_balance():
  ├─ Calls _compute_current_balance()
  ├─ Uses node_2.event_log (which is EMPTY)
  ├─ Returns checkpoint.balance (1000)
  └─ Balance: 1000 ❌ (should be 1100)

Why? get_balance() doesn't sync first!
```

### What Should Happen (FIXED):
```
node_1 deposits 100 (lazy, not propagated to node_2)
  node_1.event_log: [DepositEvent(100)]  ✓
  node_2.event_log: []  ← Empty initially

node_2.get_balance():
  ├─ Calls _sync_events()  ← SYNC FIRST!
  ├─ Fetches events from node_1 (DepositEvent)
  ├─ Merges into event_log: [DepositEvent(100)]  ← NOW IN EVENT LOG!
  ├─ Calls _compute_current_balance()
  ├─ Uses node_2.event_log (which now has deposit)
  ├─ Computes: 1000 + 100 = 1100
  └─ Balance: 1100 ✓
```

## Root Cause

**Location**: `src/core/distributed_node.py`, `get_balance()` method

**Current code**:
```python
def get_balance(self) -> Decimal:
    """Get current balance (read-only)"""
    if not self._acquire_lock(timeout=2.0):
        return self.checkpoint.balance
    
    try:
        return self._compute_current_balance()  ← No sync!
    finally:
        self._release_lock()
```

**Problem**: 
- Doesn't call `_sync_events()` before computing
- If deposits are lazy (not propagated), they won't be in the event_log
- Balance will be stale

## Withdrawal Method Does It Right (Correct)

**Location**: `src/core/distributed_node.py`, `withdraw()` method

```python
# Step 1: Sync events from all remote nodes  ← CORRECT!
remote_events = self._sync_events()

# Step 2: Merge events with deduplication
self.event_log.merge_events(remote_events)

# Step 3: Compute balance using OPTIMIZED strategy
balance_info = self.event_log.compute_balance_optimized(...)
```

**This is why withdrawals work**: They sync before computing balance!

## The Fix

Make `get_balance()` sync events before computing, just like `withdraw()` does:

```python
def get_balance(self) -> Decimal:
    """Get current balance (read-only, with event sync for lazy propagation)"""
    if not self._acquire_lock(timeout=2.0):
        return self.checkpoint.balance
    
    try:
        # Step 1: Sync events from remote nodes (for lazy-propagated deposits)
        remote_events = self._sync_events()
        
        # Step 2: Merge events
        self.event_log.merge_events(remote_events)
        
        # Step 3: Compute balance
        return self._compute_current_balance()
    finally:
        self._release_lock()
```

## Why Your Real System Reflected Changes

When you refreshed the database on another PC:
- The database might have had a full sync mechanism
- Or you manually synced databases
- Or the API was calling sync before balance check

This test reveals that the in-memory system needs explicit sync.

## Impact

**Deposits are lazy**: ✅ WORKING  
**Withdrawals propagate instantly**: ✅ WORKING  
**Balance reading with lazy deposits**: ❌ BROKEN (needs sync)

---

**SOLUTION**: Fix `get_balance()` to sync events before computing!
