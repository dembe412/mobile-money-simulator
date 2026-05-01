# Testing Guide — Mobile Money Distributed System

No Docker. No PostgreSQL. No Redis. Just Python + SQLite.

---

## Prerequisites (one-time setup)

```bash
# From project root
pip install -r requirements.txt
```

---

## Quick Start — 4 Bash Terminals

Open **4 terminals**, all in the project root `d:\mobile-money-simulator`.

### Terminal 1 — Node server_1 (port 8001)
```bash
SERVER_ID=server_1 SERVER_NAME="Node 1" SERVER_PORT=8001 python main.py
```

### Terminal 2 — Node server_2 (port 8002)
```bash
SERVER_ID=server_2 SERVER_NAME="Node 2" SERVER_PORT=8002 python main.py
```

### Terminal 3 — Node server_3 (port 8003)
```bash
SERVER_ID=server_3 SERVER_NAME="Node 3" SERVER_PORT=8003 python main.py
```

### Terminal 4 — Node server_4 (port 8004) ← optional 4th node
```bash
SERVER_ID=server_4 SERVER_NAME="Node 4" SERVER_PORT=8004 python main.py
```

> **What happens automatically:**
> - Each node creates its own `data/server_N.db` file
> - All nodes share `data/registry.db` for discovery
> - Nodes find each other within 5 seconds (no restart needed)
> - Dynamic hash ring updates as nodes join/leave

---

## Verify Cluster is Running

```bash
# Check health of each node
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8003/health

# See full cluster status (live peers, hash ring, replication stats)
curl http://127.0.0.1:8001/api/v1/cluster/status | python -m json.tool
```

---

## Create Accounts

```bash
# Create Alice on node 1
curl -X POST http://127.0.0.1:8001/api/v1/account/create \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"0700000001","account_holder_name":"Alice Mwangi","initial_balance":50000}'

# Create Bob on node 2
curl -X POST http://127.0.0.1:8002/api/v1/account/create \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"0700000002","account_holder_name":"Bob Kamau","initial_balance":50000}'

# Create Carol on node 3
curl -X POST http://127.0.0.1:8003/api/v1/account/create \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"0700000003","account_holder_name":"Carol Wanjiru","initial_balance":50000}'
```

---

## Operations

```bash
# Withdraw (asynchronous: returns request_id and accepted status)
curl -X POST http://127.0.0.1:8001/api/v1/operation/withdraw \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"0700000001","amount":1000,"client_reference":"my-unique-ref-001"}'

# Deposit (asynchronous: returns request_id and accepted status)
curl -X POST http://127.0.0.1:8002/api/v1/operation/deposit \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"0700000002","amount":500,"client_reference":"dep-ref-001"}'

# Check async request completion status (replace REQUEST_ID)
curl http://127.0.0.1:8001/api/v1/operation/request/REQUEST_ID

# Check balance
curl -X POST http://127.0.0.1:8001/api/v1/operation/balance \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"0700000001"}'

# Transfer Alice → Bob
curl -X POST http://127.0.0.1:8001/api/v1/operation/transfer \
  -H "Content-Type: application/json" \
  -d '{"from_account_id":1,"from_phone_number":"0700000001","to_phone_number":"0700000002","amount":2000,"client_reference":"txfr-001"}'

# Last 10 transactions
curl http://127.0.0.1:8001/api/v1/operation/transactions/1
```

---

## USSD Simulation

```bash
# Create account via USSD (*165*1*phone*initial_balance#)
curl -X POST http://127.0.0.1:8001/api/v1/ussd \
  -H "Content-Type: application/json" \
  -d '{"ussd_input":"*165*1*0700000099*10000#"}'

# Check balance via USSD
curl -X POST http://127.0.0.1:8001/api/v1/ussd \
  -H "Content-Type: application/json" \
  -d '{"ussd_input":"*165*3*0700000001#"}'

# Withdraw via USSD
curl -X POST http://127.0.0.1:8001/api/v1/ussd \
  -H "Content-Type: application/json" \
  -d '{"ussd_input":"*165*2*0700000001*500#"}'

# Start a persistent USSD session (returns session_id)
curl -X POST http://127.0.0.1:8001/api/v1/ussd \
  -H "Content-Type: application/json" \
  -d '{"ussd_input":"*165#","phone_number":"0700000001"}'

# Continue the same session (replace SESSION_ID with the value returned above)
curl -X POST http://127.0.0.1:8001/api/v1/ussd \
  -H "Content-Type: application/json" \
  -d '{"ussd_input":"1","phone_number":"0700000001","session_id":"SESSION_ID"}'
```

---

## Routing — Consistent Hashing

```bash
# See which node owns this phone number
curl http://127.0.0.1:8001/api/v1/routing/discover/0700000001
curl http://127.0.0.1:8001/api/v1/routing/discover/0700000002

# Hash ring status
curl http://127.0.0.1:8001/api/v1/hash-ring/status | python -m json.tool
```

---

## Stress Test (Terminal 4 or 5)

```bash
# Runs 10 concurrent clients × 20 requests each
# Tests: consistency, idempotency, replication, transfer conservation
python scripts/stress_test.py
```

---

## Verify Replication (no HTTP, reads SQLite directly)

```bash
# Compare balances across all 3 node DBs side-by-side
python scripts/verify_replication.py
```

---

## Test Dynamic Discovery — Kill/Restart a Node

```bash
# 1. With all 3 nodes running, check cluster
curl http://127.0.0.1:8001/api/v1/cluster/status | python -m json.tool

# 2. Kill Terminal 2 (Ctrl+C server_2)

# 3. Wait 15 seconds (peer TTL), then check again
curl http://127.0.0.1:8001/api/v1/cluster/status | python -m json.tool
# server_2 should be gone from active_cluster

# 4. Restart server_2 in Terminal 2
SERVER_ID=server_2 SERVER_NAME="Node 2" SERVER_PORT=8002 python main.py

# 5. Wait 5 seconds, check again — server_2 is back!
curl http://127.0.0.1:8001/api/v1/cluster/status | python -m json.tool
```

---

## Data Files

```
data/
  server_1.db   ← Node 1's isolated database
  server_2.db   ← Node 2's isolated database
  server_3.db   ← Node 3's isolated database
  registry.db   ← Shared service discovery registry (all nodes read/write)
```

To start completely fresh:
```bash
rm -rf data/
# Then restart all nodes
```

---

## Gossip Protocol Status

```bash
# Vector clocks, peer health, pending replication events
curl http://127.0.0.1:8001/api/v1/gossip/status | python -m json.tool
curl http://127.0.0.1:8002/api/v1/gossip/status | python -m json.tool
curl http://127.0.0.1:8003/api/v1/gossip/status | python -m json.tool
```
