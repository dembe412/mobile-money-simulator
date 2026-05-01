# Quick Start Guide: Event Sourcing + Checkpoint System

## 5-Minute Quick Start

### 1. Run Examples

```bash
# Navigate to project
cd d:\adone\mobile-money-simulator

# Run comprehensive examples
python scripts/example_event_sourcing.py
```

### 2. Run Tests

```bash
# Run all unit tests
pytest tests/test_event_sourcing.py -v

# Run specific test
pytest tests/test_event_sourcing.py::TestEventLog -v
```

### 3. Run Stress Tests

```bash
# Run stress test suite (takes ~30 seconds)
python scripts/stress_test_event_sourcing.py
```

---

## Key Concepts (2 Minutes)

### Event Log
- **What:** All transactions stored as immutable events
- **Why:** Complete audit trail, replay history, no data loss
- **Example:** Event(id=1, type="deposit", amount=100)

### Checkpoint
- **What:** Snapshot of processed state
- **Why:** Don't replay all history, only events since checkpoint
- **Example:** Checkpoint(balance=1000, last_event_id=50)

### Lazy Deposits
- **What:** Deposits accepted locally, propagated eventually
- **Why:** Low latency, efficient bandwidth
- **Process:** Create event → Add to log → Done

### Strong Withdrawals
- **What:** Withdrawals require sync before approval
- **Why:** Prevent double spending
- **Process:** Sync → Merge → Compute → Validate → Propagate

---

## Basic Usage (5 Minutes)

### Create System

```python
from decimal import Decimal
from src.core.distributed_system import DistributedSystem

# Create 3-node system, each starts with $1000
system = DistributedSystem(account_id=1, num_nodes=3)
```

### Deposit

```python
# Deposit $100 on node_1
success, message = system.deposit("node_1", Decimal(100))
print(f"{message}")  # "Deposit processed. Event ID: ..."

# Balance increased locally
print(system.get_balance("node_1"))  # 1100

# Other nodes don't see it yet (lazy propagation)
print(system.get_balance("node_2"))  # 1000
```

### Withdraw

```python
# Withdraw $200 from node_2
# This syncs deposits from node_1, then processes withdrawal
success, message = system.withdraw("node_2", Decimal(200))
print(f"{message}")  # "Withdrawal processed. Event ID: ..."

# After sync, node_2 sees: 1000 (initial) + 100 (node_1 deposit) - 200 = 900
print(system.get_balance("node_2"))  # 900
```

### Verify System

```python
# Check all nodes converged to same balance
converged, msg = system.verify_convergence()
print(msg)  # "All nodes converged to balance=900"

# Check no double spending
valid, msg = system.verify_no_double_spending()
print(msg)  # "No double spending: total_balance=2700"

# Print state
system.print_state()
```

---

## Idempotency (Duplicate Request Handling)

```python
# First deposit with request_id
system.deposit("node_1", Decimal(100), request_id="REQ_001")
# Balance: 1100

# Retry with SAME request_id (simulating network retry)
system.deposit("node_1", Decimal(100), request_id="REQ_001")
# REJECTED - duplicate request_id
# Balance: still 1100 (unchanged)
```

---

## Insufficient Balance

```python
# Try to withdraw more than available
system = DistributedSystem(account_id=1, num_nodes=1)
success, msg = system.withdraw("node_1", Decimal(2000))

if not success:
    print(msg)  # "Insufficient balance. Current: 1000, Requested: 2000"
    
print(system.get_balance("node_1"))  # 1000 (unchanged)
```

---

## Inspect Node State

```python
# Get detailed node information
node = system.get_node("node_1")
state = node.get_state()

print(f"Balance: {state['balance']}")
print(f"Events: {state['event_count']}")
print(f"Checkpoint: {state['checkpoint']}")
print(f"Remote nodes: {state['remote_nodes']}")

# Get all events
events = node.get_events()
for event in events:
    print(f"Event {event['event_id']}: {event['type']} ${event['amount']}")
```

---

## Common Scenarios

### Scenario: Mixed Deposits and Withdrawals

```python
system = DistributedSystem(account_id=1, num_nodes=3)

# Node 1: Deposit $200
system.deposit("node_1", Decimal(200), request_id="d1")  # 1200

# Node 2: Deposit $150
system.deposit("node_2", Decimal(150), request_id="d2")  # 1150

# Node 3: Withdraw $100 (syncs deposits from nodes 1 and 2)
system.withdraw("node_3", Decimal(100), request_id="w1")
# Sees: 1000 + 200 + 150 = 1350
# After: 1350 - 100 = 1250

# All nodes converge
converged, msg = system.verify_convergence()
assert converged
```

### Scenario: Sequential Operations

```python
system = DistributedSystem(account_id=1, num_nodes=1)

# Sequence: deposit, deposit, withdraw, withdraw
system.deposit("node_1", Decimal(100))  # 1100
system.deposit("node_1", Decimal(50))   # 1150
system.withdraw("node_1", Decimal(75))  # 1075
system.withdraw("node_1", Decimal(25))  # 1050

print(system.get_balance("node_1"))  # 1050
```

---

## Stress Testing

```python
from scripts.stress_test_event_sourcing import StressTestRunner

# High load test
runner = StressTestRunner(num_nodes=10, num_operations=1000)
runner.run_stress_test(num_threads=20)

# Results:
# - Ops/sec
# - Latencies (min, max, avg)
# - Convergence verification
# - Double spending check
```

---

## Architecture Cheat Sheet

| Aspect | Details |
|--------|---------|
| **Event** | Immutable transaction record |
| **Checkpoint** | Balance snapshot at specific event |
| **Deposit** | Local + lazy (eventual consistency) |
| **Withdraw** | Sync + strong consistency |
| **Sync** | Fetch events after checkpoint |
| **Dedup** | By event_id + request_id |
| **Lock** | Per-node thread safety |

---

## Performance Notes

- **Deposits:** O(1) latency - instant, no network
- **Withdrawals:** O(N) where N = remote nodes
- **Balance computation:** O(M) where M = events since checkpoint
- **Bandwidth:** O(M) instead of O(total_events)

---

## Troubleshooting

### "Insufficient balance" when balance seems high

→ Withdrawal syncs events from all nodes first. Your balance includes pending deposits.

### Balances don't match across nodes

→ Call `verify_convergence()` to check. After withdrawal (which propagates), all should match.

### Duplicate request rejected

→ This is correct! Same request_id means idempotent retry. Use different request_id for new operation.

### Need to inspect events

→ Use `node.get_events()` to see all events, or `node.get_state()` for summary.

---

## Files to Explore

| File | Purpose |
|------|---------|
| `src/core/checkpoint.py` | Checkpoint implementation |
| `src/core/event_log.py` | Event storage and queries |
| `src/core/distributed_node.py` | Single node logic |
| `src/core/distributed_system.py` | Multi-node coordination |
| `tests/test_event_sourcing.py` | Unit tests (great examples) |
| `scripts/example_event_sourcing.py` | 6 detailed examples |
| `scripts/stress_test_event_sourcing.py` | Load testing |
| `EVENT_SOURCING_ARCHITECTURE.md` | Full design docs |

---

## Next Steps

1. **Understand the architecture**: Read `EVENT_SOURCING_ARCHITECTURE.md`
2. **Run examples**: `python scripts/example_event_sourcing.py`
3. **Run tests**: `pytest tests/test_event_sourcing.py -v`
4. **Stress test**: `python scripts/stress_test_event_sourcing.py`
5. **Inspect code**: Look at `src/core/distributed_node.py` for core logic

---

## Key Guarantees

✅ **No double spending** - withdrawals require sync  
✅ **Eventual consistency** - deposits lazy  
✅ **No balance corruption** - immutable events  
✅ **Idempotency** - retries handled  
✅ **Convergence** - all nodes agree eventually  
✅ **Auditability** - complete event log  

---

## Questions?

- Check `EVENT_SOURCING_ARCHITECTURE.md` for design details
- Review `tests/test_event_sourcing.py` for edge cases
- Run `scripts/example_event_sourcing.py` for working examples
