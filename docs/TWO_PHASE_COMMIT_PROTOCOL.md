# Two-Phase Commit (2PC) Protocol for Coordinated Withdrawals

## The Problem

Your original concern is **critical and valid**:

```
Scenario: User withdraws on node_1
├─ node_1: Applies withdrawal immediately ✓
├─ node_2: Waiting for replication...
├─ node_1: CRASHES before propagating to node_2, node_3 ✗
└─ Result: INCONSISTENT STATE
   • node_1: balance = 900 (withdrawal applied)
   • node_2: balance = 1000 (withdrawal NOT applied)
   • node_3: balance = 1000 (withdrawal NOT applied)
```

This violates the fundamental principle of distributed systems: **all replicas should maintain consistent state**.

---

## The Solution: Two-Phase Commit (2PC)

The 2PC protocol ensures **atomic all-or-nothing semantics** across all replicas:

### Protocol Phases

#### Phase 1: PREPARE (Voting Round)
```
Coordinator (node_1) sends to all replicas:
  "Can you withdraw 100? Lock the funds and validate balance."

Replica behavior:
  1. Acquire lock on account
  2. Sync latest events from other replicas
  3. Compute current balance (including pending locked funds)
  4. Validate: balance >= amount
  5. If OK: Vote ACK, lock the funds
     If NOT OK: Vote NACK, release lock
  6. Send vote back to coordinator

Coordinator collects votes from ALL replicas
```

#### Phase 2: COMMIT or ROLLBACK (All-or-Nothing)
```
Coordinator evaluates votes:
  ✓ If ALL vote ACK:
    → Send COMMIT to all replicas
    → Each replica applies the withdrawal
    
  ✗ If ANY vote NACK or TIMEOUT:
    → Send ROLLBACK to all replicas
    → Each replica releases locks, discards prepared state
```

#### Phase 3: FINALIZE (Cleanup)
```
Coordinator releases transaction locks and cleans up state
```

---

## Implementation Details

### 1. **Coordinated Commit Manager** (`src/core/coordinated_commit.py`)

Manages the state machine of the 2PC protocol:

```python
class CoordinatedCommitManager:
    def create_transaction(account_id, amount, request_id, replica_ids)
        → Creates new transaction, acquires account lock
    
    def record_prepare_vote(transaction_id, replica_id, vote)
        → Tracks votes from each replica (ACK, NACK, TIMEOUT)
    
    def can_commit(transaction_id, total_replicas)
        → Evaluates if all conditions met to commit
    
    def commit_transaction(transaction_id)
        → Moves transaction to COMMIT phase
    
    def rollback_transaction(transaction_id, reason)
        → Moves transaction to ROLLBACK phase
```

### 2. **Enhanced Distributed Node** (`src/core/distributed_node.py`)

Three new methods for 2PC protocol:

#### **Coordinator Side: `coordinated_withdraw()`**
```python
def coordinated_withdraw(amount, request_id) -> (bool, str):
    """Main entry point for coordinated withdrawal"""
    
    # Step 1: Create transaction and acquire account lock
    txn_id = create_transaction(...)
    
    # Step 2: PREPARE PHASE
    for each replica:
        vote = replica.prepare_for_coordinated_withdraw(txn_id, amount, ...)
        record_vote(txn_id, replica_id, vote)
    
    # Step 3: Evaluate votes
    if all_votes_ACK:
        # Step 4: COMMIT PHASE
        for each replica:
            replica.commit_coordinated_withdraw(txn_id)
        return True, "Success"
    else:
        # Step 4: ROLLBACK PHASE
        for each replica:
            replica.rollback_coordinated_withdraw(txn_id)
        return False, f"Rolled back: {reason}"
    
    # Step 5: FINALIZE
    cleanup_transaction_state(txn_id)
```

#### **Replica Side: `prepare_for_coordinated_withdraw()`**
```python
def prepare_for_coordinated_withdraw(txn_id, amount, ...) -> ReplicaVote:
    """Prepare phase: validate and lock funds"""
    
    # 1. Sync latest events from all replicas
    remote_events = sync_events()
    
    # 2. Compute current available balance
    current_balance = compute_balance_optimized(...)
    available = current_balance - sum(already_locked_funds)
    
    # 3. Validate
    if available >= amount:
        # Lock funds and prepare event
        locked_funds[txn_id] = amount
        prepared_transactions[txn_id] = event
        return ReplicaVote.ACK
    else:
        return ReplicaVote.NACK
```

#### **Replica Side: `commit_coordinated_withdraw()`**
```python
def commit_coordinated_withdraw(txn_id) -> (bool, str):
    """Commit phase: apply the withdrawal"""
    
    event = prepared_transactions[txn_id]
    
    # 1. Add event to log
    event_log.add_event(event)
    
    # 2. Update checkpoint
    checkpoint.balance -= event.amount
    save_checkpoint()
    
    # 3. Clean up transaction state
    del locked_funds[txn_id]
    del prepared_transactions[txn_id]
    
    return True, "Committed"
```

#### **Replica Side: `rollback_coordinated_withdraw()`**
```python
def rollback_coordinated_withdraw(txn_id) -> (bool, str):
    """Rollback phase: release locks and discard state"""
    
    # 1. Release locks
    if txn_id in locked_funds:
        del locked_funds[txn_id]
    
    # 2. Discard prepared state
    if txn_id in prepared_transactions:
        del prepared_transactions[txn_id]
    
    return True, "Rolled back"
```

### 3. **Transaction State Tracking**

Each node maintains three data structures:

```python
# In DistributedNode
self.locked_funds: Dict[str, Decimal]           # {txn_id: locked_amount}
    ├─ Prevents double-spending during prepare phase
    └─ Example: {txn_123: 100}

self.prepared_transactions: Dict[str, Event]     # {txn_id: event}
    ├─ Stores prepared but not-yet-committed events
    └─ Kept in memory until commit/rollback

self.coordinated_commit_manager: CoordinatedCommitManager
    ├─ Tracks transaction state machine
    ├─ Counts votes (ACK, NACK, TIMEOUT)
    └─ Enforces all-or-nothing semantics
```

---

## Example Walkthrough

### Scenario: Withdraw 100 with 3 replicas

```
Initial State (all nodes):
  node_1: balance=1000, locked_funds={}
  node_2: balance=1000, locked_funds={}
  node_3: balance=1000, locked_funds={}


STEP 1: Coordinator (node_1) calls coordinated_withdraw(100)
  ✓ Creates transaction txn_001
  ✓ Acquires account_1 lock

  
STEP 2: PREPARE PHASE
  Coordinator sends: prepare_for_coordinated_withdraw(txn_001, 100)
  
  Node_1 (self):
    1. Sync events: [no new events]
    2. Balance = 1000
    3. Available = 1000 - 0 = 1000 >= 100 ✓
    4. Locks 100: locked_funds[txn_001] = 100
    5. Creates event: prepared_transactions[txn_001] = event
    6. Votes: ACK ✓
  
  Node_2 (replica):
    1. Sync events: [event from node_1 deposit]
    2. Balance = 1000
    3. Available = 1000 - 0 = 1000 >= 100 ✓
    4. Locks 100: locked_funds[txn_001] = 100
    5. Creates event: prepared_transactions[txn_001] = event
    6. Votes: ACK ✓
  
  Node_3 (replica):
    1. Sync events: [no new events]
    2. Balance = 1000
    3. Available = 1000 - 0 = 1000 >= 100 ✓
    4. Locks 100: locked_funds[txn_001] = 100
    5. Creates event: prepared_transactions[txn_001] = event
    6. Votes: ACK ✓
  
  Coordinator receives: {node_1: ACK, node_2: ACK, node_3: ACK}


STEP 3: COMMIT PHASE
  All nodes voted ACK → COMMIT!
  
  Coordinator sends: commit_coordinated_withdraw(txn_001)
  
  Node_1:
    1. Applies event: event_log.add_event(event)
    2. Updates checkpoint: balance -= 100 → 900
    3. Clears state: del locked_funds[txn_001], del prepared_transactions[txn_001]
    4. Saves checkpoint
  
  Node_2:
    1. Applies event: event_log.add_event(event)
    2. Updates checkpoint: balance -= 100 → 900
    3. Clears state: del locked_funds[txn_001], del prepared_transactions[txn_001]
    4. Saves checkpoint
  
  Node_3:
    1. Applies event: event_log.add_event(event)
    2. Updates checkpoint: balance -= 100 → 900
    3. Clears state: del locked_funds[txn_001], del prepared_transactions[txn_001]
    4. Saves checkpoint


Final State (all nodes):
  ✓ node_1: balance=900, locked_funds={}
  ✓ node_2: balance=900, locked_funds={}
  ✓ node_3: balance=900, locked_funds={}
  
  CONSISTENT! All nodes applied the same transaction.
```

---

## Failure Scenarios

### Scenario 1: Insufficient Balance on One Replica

```
Node_2 state: balance=50 (manually depleted)

PREPARE PHASE:
  node_1: available=1000, votes ACK
  node_2: available=50 < 100, votes NACK ✗
  node_3: available=1000, votes ACK


COMMIT PHASE EVALUATION:
  ✗ At least one NACK received
  → ABORT PHASE: Send ROLLBACK to all


ROLLBACK:
  node_1: 
    - Release lock: del locked_funds[txn_001]
    - Discard event: del prepared_transactions[txn_001]
    - Balance remains: 1000
  
  node_2:
    - Release lock: del locked_funds[txn_001]
    - Discard event: del prepared_transactions[txn_001]
    - Balance remains: 50
  
  node_3:
    - Release lock: del locked_funds[txn_001]
    - Discard event: del prepared_transactions[txn_001]
    - Balance remains: 1000


RESULT: ✓ No partial state!
  - ALL nodes rolled back
  - Balances unchanged
  - System protected from inconsistency
```

### Scenario 2: Coordinator Crashes After Prepare

```
Coordinator (node_1) crashes after collecting all ACK votes,
before sending COMMIT messages.


Replica behavior (automatic timeout recovery):
  node_2:
    - Waiting for COMMIT/ROLLBACK from coordinator
    - Timeout after 5 seconds
    - Automatically ROLLBACK: release locks, discard state
  
  node_3:
    - Same as node_2


RESULT: ✓ Automatic recovery!
  - Replicas don't hang forever
  - Stale locks released after timeout
  - System remains healthy
```

---

## Key Guarantees

| Guarantee | How 2PC Achieves It |
|-----------|-------------------|
| **Atomicity** | All-or-nothing: COMMIT only if all replicas vote ACK |
| **Consistency** | Locks prevent concurrent modifications; validation ensures soundness |
| **Isolation** | Locked funds isolated; prepared state separate from applied state |
| **Durability** | Events persisted to checkpoints after COMMIT phase |
| **No Double-Spending** | Locked funds reserved; concurrent withdrawals serialized |

---

## Comparison: Before vs. After

### BEFORE: Lazy Propagation (Event Sourcing Alone)

```
Withdrawal operation:
  1. Apply locally immediately ✓
  2. Send events to replicas asynchronously
  3. If coordinator crashes: replicas never get event
  
Result: INCONSISTENT STATE ✗
```

### AFTER: 2PC Coordinated Withdrawal

```
Withdrawal operation:
  1. PREPARE: All replicas lock and validate
  2. COMMIT: All apply together (or ROLLBACK together)
  3. FINALIZE: Clean up
  
Result: GUARANTEED CONSISTENCY ✓
```

---

## Usage

```python
from src.core.distributed_system import DistributedSystem

system = DistributedSystem(num_nodes=3)

# Old way (lazy propagation, potentially inconsistent)
# success, msg = system.nodes['node_1'].withdraw(amount=100, request_id="w1")

# New way (2PC coordinated, guaranteed consistent)
success, msg = system.nodes['node_1'].coordinated_withdraw(
    amount=Decimal(100),
    request_id="withdraw_001"
)

if success:
    print("✓ All replicas consistently applied the withdrawal")
else:
    print("✗ Transaction rolled back on all replicas")
```

---

## Summary

The 2PC protocol **solves the critical consistency problem** in your distributed mobile money system:

✅ **Eliminates inconsistency** when coordinator crashes mid-propagation  
✅ **Prevents double-spending** with explicit locks during prepare  
✅ **Provides all-or-nothing semantics** across all replicas  
✅ **Handles failures gracefully** with automatic timeouts and rollbacks  
✅ **Maintains strong consistency** at the cost of slightly higher latency  

This is production-grade transaction semantics for distributed systems.
