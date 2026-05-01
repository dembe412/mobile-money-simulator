# Mobile Money System - Distributed P2P Payment Platform

A production-ready **distributed mobile money system** that simulates real-world payment infrastructure like M-Pesa. Built with Python, FastAPI, and PostgreSQL, it implements cutting-edge distributed systems patterns to handle millions of concurrent transactions across multiple servers while maintaining data consistency and preventing financial fraud.

## 📋 What This System Solves

This system addresses critical challenges in building **fault-tolerant financial platforms**:

- **High Availability**: If one server fails, others continue serving customers
- **Data Safety**: No money is lost due to crashes or network failures
- **Consistency**: Prevents double-charging and overdrafts even with concurrent requests
- **Feature Phone Support**: Works on basic USSD (Unstructured Supplementary Service Data) phones without internet
- **Scalability**: Load distributes automatically across multiple servers based on customer phone numbers

## 🏗️ Core Distributed Systems Concepts

### 1. **Eventual Consistency** (Why Not Immediate Consistency?)

In a traditional single-database system, when you transfer money from Account A to Account B, both updates happen instantly. But in a **distributed system**, servers are geographically separated and network delays exist. We have two options:

- **Strong Consistency**: Block until all servers agree (slow, blocks customers on network problems)
- **Eventual Consistency**: Process immediately, then sync servers in background (fast, eventually all servers have same state)

**This system uses eventual consistency** because a payment shouldn't be blocked by network delays. Users get instant confirmation, and the system syncs in the background.

### 2. **Consistent Hashing** (Why Route to Specific Servers?)

Imagine 1 million customers trying to transfer money. We can't keep all data on one server. Solution: **divide customers by phone number**.

**Consistent Hashing** maps each phone number to a specific server:
- Phone `075346363` → Server 2 (primary)
- Phone `0721234567` → Server 1 (primary)

**Benefits:**
- **Automatic Load Balancing**: Customers spread evenly across servers
- **Fault Tolerance**: If server 2 dies, we query server 1 for customer's backup data
- **Fast Lookups**: O(log n) instead of searching all servers
- **No Central Registry**: Any server can route requests without central coordination

### 3. **Pessimistic Locking** (Why Lock Accounts During Transactions?)

Without locks, imagine this nightmare scenario:
```
Time 1: Thread A reads balance = 1000 KES
Time 2: Thread B reads balance = 1000 KES
Time 3: Thread A withdraws 500 → balance = 500 (writes)
Time 4: Thread B withdraws 600 → balance = 400 (writes)
Result: Balance is 400, but 1100 was withdrawn! (Double charge)
```

**Pessimistic Locking** prevents this:
```
Time 1: Thread A LOCKS account
Time 2: Thread A reads balance = 1000 KES
Time 3: Thread A withdraws 500 → balance = 500 (writes)
Time 4: Thread A UNLOCKS account
Time 5: Thread B can now acquire lock and read correct balance
Result: Correct balance of 500
```

### 4. **Request Idempotency** (Why Track Request IDs?)

Mobile networks lose packets. A customer might tap "Send Money" when their network is weak. The phone sends the request 3 times. Without idempotency:
```
Result: 3x charges! (Money sent 3 times)
```

With request IDs:
```
Request 1: Process normally, save request_id → balance = 900
Request 2: See request_id already processed → return cached balance = 900
Request 3: See request_id already processed → return cached balance = 900
Result: Charged only once
```

### 5. **Vector Clocks** (Why Track Event Ordering?)

In distributed systems, events happen on different servers. Imagine:
- Server 1: Withdraw 100 KES
- Server 2: Withdraw 100 KES

Did they happen at the same time (concurrent) or in sequence? **Vector clocks** answer this:

```
Server 1 VC: {server_1: 1, server_2: 0, server_3: 0}  = "Withdraw 100"
Server 2 VC: {server_1: 1, server_2: 1, server_3: 0}  = "Withdraw 100"

Comparison shows Server 2's event happened AFTER Server 1's event
(Server 2 saw Server 1's update before its own event)
```

### 6. **Event Sourcing & Write-Ahead Logs** (Why Record Everything?)

Instead of just storing current balance, we store **all operations**:
```
Operation 1 (Time 10:00): Withdraw 100 → Balance: 900
Operation 2 (Time 10:01): Deposit 50 → Balance: 950
Operation 3 (Time 10:02): Withdraw 200 → Balance: 750
```

**Benefits:**
- **Crash Recovery**: If server dies after writing to disk but before applying to memory, replay WAL on restart
- **Audit Trail**: Full transaction history
- **Replication**: Sync by replaying events

### 7. **Quorum-Based Replication** (Why Replicate to Quorum?)

After processing a withdrawal, we replicate to other servers. But how many confirmations do we need?

**Quorum = N/2 + 1** (majority wins)

- 3 servers: 2 confirmations needed
- 5 servers: 3 confirmations needed

**Why majority?** Even if one server lies or crashes, the majority always agrees on truth.

### 8. **Conflict Resolution** (What If Two Servers Process Same Transaction?)

With eventual consistency, two servers might both process the same transaction. Who wins?

**Last-Write-Wins (LWW)** strategy: The operation with later timestamp wins.
```
Server 1 withdraws 100 at 10:00:00.001
Server 2 withdraws 100 at 10:00:00.002

Result: Server 2's operation wins, Server 1's is ignored
```

## 📋 Features

- **Distributed P2P Architecture**: Multiple equal-peer servers for high availability
- **Consistent Hashing**: Route clients to optimal server based on phone number
- **Pessimistic Locking**: Prevent race conditions in concurrent operations
- **Request Idempotency**: Exactly-once semantics with unique request IDs
- **Vector Clocks**: Detect concurrent operations for conflict resolution
- **Event Sourcing**: Complete audit trail and crash recovery
- **Write-Ahead Logging**: Durability guarantee - no data loss
- **Quorum-Based Replication**: Majority consensus for eventual consistency
- **Gossip Protocol**: P2P heartbeats and event propagation
- **USSD Protocol Support**: Feature phone accessibility
- **Persistent USSD Sessions**: Menu-driven server-side sessions with session IDs
- **Operations**: Withdraw, Deposit, Check Balance, Mini Statement
- **Automatic Failover**: Clients retry on alternate servers
- **Conflict Resolution**: Last-Write-Wins strategy for diverged states

## 🏗️ System Architecture

```
        CLIENTS (USSD/API/Web)
             ↓
    ┌────────┼────────┐
    ↓        ↓        ↓
 Server_1  Server_2  Server_3
 (8001)    (8002)    (8003)
    │        │        │
    └────────┼────────┘
             ↓
      PostgreSQL Database
      (Shared Persistence)
        │
        ├─ Accounts Table
        ├─ Transactions Table
        ├─ Events Table (Event Log)
        └─ Locks Table (Concurrency)
        
    P2P Gossip Network
    ├─ Heartbeats (every 5 sec)
    ├─ Event Broadcasts
    └─ State Synchronization
```

### Layer Breakdown

**1. Client Layer**: Phones, web apps, API clients
- USSD gateway: Basic phones (no internet)
- REST API: Smartphones, other services
- Mobile client library: Direct SDK integration

**2. Server Layer**: Three independent servers
- Each server is identical and peer-equal
- No master/slave hierarchy
- Direct HTTP gossip communication
- Shared PostgreSQL database

**3. Database Layer**: PostgreSQL
- **Accounts**: Current balance, phone number, status
- **Transactions**: All financial operations with full audit trail
- **Events**: Event sourcing log for replication and recovery
- **Locks**: Pessimistic locks for concurrent operation safety
- **Requests**: Idempotency cache with request IDs

**4. Gossip Network**: P2P synchronization
- Servers send heartbeats (I'm alive)
- Servers broadcast new events (sync data)
- Servers detect failures (heartbeat timeout = server offline)

## 📊 Data Flow: Withdraw Operation

Let's trace a real withdrawal to understand how all components work together:

```
Customer dials: *165*2*0751234567*1000#  (Withdraw 1000 KES)
                  │
                  ├─ 1. USSD Gateway receives request
                  │
                  ├─ 2. Route to Server
                  │     ├─ Hash phone number: 0751234567
                  │     └─ Get primary server for this phone
                  │        Result: Server 2 (primary) [Server 1, 3 are backups]
                  │
                  ├─ 3. Check Idempotency Cache (Server 2)
                  │     ├─ Generate request_id from phone + operation + reference
                  │     ├─ Query requests table
                  │     └─ If duplicate: Return cached response immediately
                  │
                  ├─ 4. Acquire Pessimistic Lock
                  │     ├─ INSERT into locks table with:
                  │     │   - account_id = 1
                  │     │   - request_id = <unique_id>
                  │     │   - locked_at = NOW
                  │     │   - timeout = 30 seconds
                  │     └─ Other threads must wait for lock release
                  │
                  ├─ 5. Validate & Check Balance
                  │     ├─ Query accounts table
                  │     ├─ Current balance = 5000 KES
                  │     ├─ Check: 5000 >= 1000? YES
                  │     └─ Insufficient balance check prevents overdraft
                  │
                  ├─ 6. Create Event (Event Sourcing)
                  │     ├─ Event = {
                  │     │   type: "WITHDRAW",
                  │     │   account_id: 1,
                  │     │   amount: 1000,
                  │     │   timestamp: <now>,
                  │     │   server_id: "server_2",
                  │     │   vector_clock: {server_1: 0, server_2: 5, server_3: 0},
                  │     │   event_id: <uuid>
                  │     │ }
                  │     └─ Save to events table
                  │
                  ├─ 7. Write to Write-Ahead Log
                  │     ├─ Append to WAL before applying
                  │     ├─ Mark status = PENDING
                  │     └─ Ensures recovery if crash happens next
                  │
                  ├─ 8. Apply to In-Memory State
                  │     ├─ Update accounts.balance:
                  │     │   5000 - 1000 = 4000
                  │     └─ Mark WAL entry as APPLIED
                  │
                  ├─ 9. Cache Response
                  │     ├─ Save to requests table with:
                  │     │   - request_id = <same_id_from_step_4>
                  │     │   - response = {success, balance: 4000}
                  │     │   - ttl = 24 hours (prevents duplicate charges)
                  │     └─ Next identical request gets cached response
                  │
                  ├─ 10. Release Lock
                  │      └─ DELETE from locks table
                  │
                  ├─ 11. Return Response to Customer
                  │      └─ *165*2*Success*NewBal:4000#
                  │
                  └─ 12. ASYNC - Replicate to Other Servers
                         ├─ Server 2 sends event to Server 1:
                         │   POST /gossip/event_broadcast
                         │   Payload: {event_id, account_id, amount, ...}
                         │
                         ├─ Server 1 receives:
                         │   ├─ Check vector clock (causality)
                         │   ├─ Apply event to own state
                         │   ├─ Send ACK back
                         │   └─ Update vector clock
                         │
                         ├─ Server 2 sends event to Server 3:
                         │   (same process)
                         │
                         └─ Once 2/3 servers ACK:
                            └─ Mark in WAL as REPLICATED
                               (now safe from data loss even with 1 crash)
```

### Why Each Step Matters

1. **Route Correctly**: Ensures one server owns this customer's data
2. **Check Cache**: Prevents duplicate charges from flaky networks
3. **Acquire Lock**: Prevents race conditions with concurrent operations
4. **Validate**: Stops overdrafts and fraud
5. **Event Sourcing**: Creates audit trail and enables recovery
6. **Write-Ahead Log**: Durability - even if crash, we have record
7. **Apply Change**: Updates in-memory state quickly
8. **Cache Response**: Handles network retries without re-processing
9. **Release Lock**: Allows next operation to proceed
10. **Return Immediately**: Customer gets instant feedback
11. **Replicate Async**: Sync other servers without blocking customer

This design ensures:
- **Consistency**: Locks prevent double-charging
- **Durability**: WAL protects against crashes
- **Availability**: Replication ensures data survives server failures
- **Performance**: Customer gets instant response without waiting for replication

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**: The application language
- **PostgreSQL 12+**: Distributed database storing all financial data
- **Redis 7+** (Optional): For session caching and performance
- **Docker & Docker Compose** (Recommended): Simplest way to run everything

### Installation

#### Option A: Docker Compose (Recommended for Development)

```bash
git clone <repo>
cd mobile-money-simulator

# Start all services
docker-compose up

# In new terminal, verify services are ready
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

This starts:
- 3 Mobile Money Servers (ports 8001, 8002, 8003)
- PostgreSQL database
- All services auto-initialized

#### Option B: Manual Installation (Windows/Mac/Linux)

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Set up PostgreSQL
# macOS:
brew install postgresql
brew services start postgresql

# Windows:
# Download from: https://www.postgresql.org/download/windows/
# Or use: choco install postgresql

# Linux (Ubuntu):
sudo apt-get install postgresql postgresql-contrib
sudo service postgresql start

# 3. Create database
createdb mobile_money_system
# If using Docker:
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15

# 4. Initialize tables
python init_database.py

# 5. Start servers (in separate terminals)

# Terminal 1 - Server 1
set SERVER_ID=server_1 && set SERVER_PORT=8001 && python main.py

# Terminal 2 - Server 2
set SERVER_ID=server_2 && set SERVER_PORT=8002 && python main.py

# Terminal 3 - Server 3
set SERVER_ID=server_3 && set SERVER_PORT=8003 && python main.py
```

#### Option C: Environment Variables

Create `.env` file:
```env
# Server Configuration
SERVER_ID=server_1
SERVER_PORT=8001
SERVER_HOST=localhost

# Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=mobile_money_system

# Redis (optional)
REDIS_HOST=localhost
REDIS_PORT=6379

# Application
APP_ENV=development
LOG_LEVEL=INFO
```

### Verify Installation

```bash
# Check all servers are running
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health

# Expected response:
# {"status": "healthy", "server_id": "server_1", "timestamp": "2026-04-19T10:00:00"}

# Check hash ring status (consistent hashing)
curl http://localhost:8001/api/v1/hash-ring/status
```

## 💳 Usage Examples

### 1. USSD (For Feature Phones)

USSD is the protocol used by basic phones without internet. Format: `*165*OPERATION*PHONE*AMOUNT#`

#### Create Account
```
Input:  *165*1*0751234567*10000#
        (Operation 1 = Create, Phone = 0751234567, Amount = 10000 KES)

Output: *165*1*Success*Account:12345#
        (Account created with ID 12345)
```

#### Withdraw
```
Input:  *165*2*0751234567*1000#
        (Operation 2 = Withdraw, Amount = 1000 KES)

Output: *165*2*Success*NewBal:9000#
        (Withdrew 1000, new balance is 9000)
```

#### Check Balance
```
Input:  *165*3*0751234567#
        (Operation 3 = Balance check)

Output: *165*3*Balance:9000#
```

#### Mini Statement (Last 5 transactions)
```
Input:  *165*4*0751234567#
        (Operation 4 = Mini statement)

Output: *165*4*1.Withdraw:1000(10:00)*
        2.Deposit:500(11:30)*
        3.Withdraw:100(12:00)#
```

### 2. REST API (For Web/Mobile Apps)

#### Create Account
```bash
curl -X POST http://localhost:8001/api/v1/account/create \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "0751234567",
    "account_holder_name": "John Doe",
    "initial_balance": 10000.0
  }'

# Response (201 Created):
{
  "account_id": 1,
  "phone_number": "0751234567",
  "account_holder_name": "John Doe",
  "balance": 10000.0,
  "created_at": "2026-04-19T10:00:00",
  "status": "active"
}
```

#### Withdraw (Asynchronous Messaging + Idempotency)
```bash
curl -X POST http://localhost:8001/api/v1/operation/withdraw \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "phone_number": "0751234567",
    "amount": 1000.0,
    "client_reference": "mobile_app_v1_ref_123"
  }'

# Response (200 OK - accepted for async processing):
{
  "status": "accepted",
  "message": "Withdrawal request queued for asynchronous processing",
  "request_id": "ref_0751234567_mobile_app_v1_ref_123",
  "processing_status": "received",
  "check_status_url": "/api/v1/operation/request/ref_0751234567_mobile_app_v1_ref_123"
}

# Poll request status until processing_status is completed or failed
curl http://localhost:8001/api/v1/operation/request/ref_0751234567_mobile_app_v1_ref_123

# If same request sent again (same client_reference):
# Server returns SAME response without charging twice!
```

#### Check Balance
```bash
curl -X GET http://localhost:8001/api/v1/account/1

# Response (200 OK):
{
  "account_id": 1,
  "phone_number": "0751234567",
  "account_holder_name": "John Doe",
  "balance": 9000.0,
  "last_transaction": "2026-04-19T10:05:00"
}
```

#### Get Mini Statement
```bash
curl -X GET http://localhost:8001/api/v1/account/1/statement?limit=5

# Response (200 OK):
{
  "account_id": 1,
  "transactions": [
    {
      "transaction_id": "txn_abc123",
      "type": "withdraw",
      "amount": 1000.0,
      "balance_after": 9000.0,
      "timestamp": "2026-04-19T10:05:00"
    },
    {
      "transaction_id": "txn_xyz789",
      "type": "deposit",
      "amount": 500.0,
      "balance_after": 10000.0,
      "timestamp": "2026-04-19T10:00:00"
    }
  ]
}
```

#### Server Discovery (Consistent Hashing)
```bash
curl http://localhost:8001/api/v1/routing/discover/0751234567

# Response shows which server should handle this phone:
{
  "phone_number": "0751234567",
  "primary_server": {
    "server_id": "server_2",
    "host": "localhost",
    "port": 8002,
    "url": "http://localhost:8002"
  },
  "replica_servers": [
    {
      "server_id": "server_1",
      "host": "localhost",
      "port": 8001
    },
    {
      "server_id": "server_3",
      "host": "localhost",
      "port": 8003
    }
  ],
  "hash_value": 45678  # Position on hash ring
}
```

### 3. Python Client Library

```python
from client.mobile_money_client import MobileMoneyClient

# Initialize with all servers (for failover)
client = MobileMoneyClient(
    server_urls=[
        "http://localhost:8001",
        "http://localhost:8002",
        "http://localhost:8003"
    ]
)

# Create account
success, response = client.create_account(
    phone_number="0751234567",
    account_holder_name="John Doe",
    initial_balance=10000.0
)
print(f"Created: {response}")

# Withdraw
success, response = client.withdraw(
    account_id=1,
    phone_number="0751234567",
    amount=1000.0,
    client_reference="app_ref_123"  # Unique per request for idempotency
)
print(f"Withdraw: {response}")

# Check balance
success, response = client.check_balance(account_id=1)
print(f"Balance: {response['balance']}")

# Deposit
success, response = client.deposit(
    account_id=1,
    phone_number="0751234567",
    amount=500.0,
    client_reference="app_ref_124"
)
print(f"Deposit: {response}")

# Mini statement
success, response = client.get_statement(account_id=1, limit=5)
print(f"Transactions: {response['transactions']}")

# USSD
success, response = client.ussd_request("*165*2*0751234567*1000#")
print(f"USSD Response: {response['ussd_response']}")
```
## 🔄 P2P Replication & Gossip Protocol

### How Replication Works

After a transaction is processed locally, it replicates to other servers to prevent data loss:

```
TIME 1 (T=0ms):
  Customer withdraws 1000 KES on Server 2
  → Transaction recorded locally
  → Balance = 9000
  
TIME 2 (T=50ms):
  Server 2 sends WITHDRAW event to Server 1 & Server 3
  Payload: {event_id, account_id, amount, timestamp, vector_clock}
  
TIME 3 (T=100ms):
  Server 1 receives event
  → Checks vector clock (causality order)
  → Applies event to its database
  → Sends ACK back
  
TIME 4 (T=150ms):
  Server 3 receives event
  → Applies event
  → Sends ACK
  
TIME 5 (T=200ms):
  Server 2 receives 2/3 ACKs (quorum reached!)
  → Marks event as "REPLICATED" (safe now)
  → If Server 2 crashes tomorrow, data survives on Server 1 & 3

CUSTOMER SEES: Response at T=100ms (doesn't wait for replication)
SYSTEM GUARANTEES: Data safe after T=200ms
```

### Gossip Protocol Details

Servers maintain contact via gossip heartbeats:

```
HEARTBEAT MESSAGE (every 5 seconds):

Server 2 → Server 1:
{
  "message_type": "heartbeat",
  "from_server": "server_2",
  "vector_clock": {"server_1": 5, "server_2": 15, "server_3": 4},
  "sync_position": 23456,  # Up to which event I've seen
  "status": "healthy",
  "latency_ms": 45,
  "timestamp": "2026-04-19T10:05:00Z"
}

Server 1 receives & updates:
- Last contact from server_2 = NOW
- Knows server_2 has seen events up to #23456
- Can calculate: Server_1 is 3 events ahead, should sync
```

### Quorum-Based Replication

Why require 2 out of 3 confirmations?

**Scenario: 1 Server Lies or Crashes**

```
3 Servers: S1, S2, S3

Withdraw 1000 happens on S2:
  S2 → Process locally ✓
  S2 → Send to S1 & S3
  
Possible outcomes:

1. BEST CASE (2 ACK):
   S1: ACK ✓
   S3: ACK ✓
   → Quorum reached, safe forever
   
2. ONE SERVER DOWN:
   S1: ACK ✓
   S3: Network error (DOWN)
   → Still 2/3 (S2+S1), quorum reached
   
3. WORST CASE (all servers up but one acts weird):
   S1: ACK ✓
   S3: NACK (says balance would go negative)
   → Majority agrees (2 ACK vs 1 NACK), ignore S3
   
4. NETWORK PARTITION:
   S1: Unreachable
   S3: Unreachable
   → Cannot reach quorum
   → Operation aborts (fails safe - no money lost)
   → When network recovers, retry succeeds
```

**Why majority always wins:**
- Total = 3, Majority = 2
- If you have 2 servers, you have the truth
- If one server crashes = you still have 2
- If two servers crash = you fail gracefully (no fake truth)

### Conflict Resolution When Servers Diverge

In a distributed system, two servers might process different operations concurrently:

```
TIME 0:
  S1 Balance: 1000
  S2 Balance: 1000

TIME 1 (happens simultaneously):
  S1: Withdraw 600 (1000 - 600 = 400)
  S2: Withdraw 700 (1000 - 700 = 300)

TIME 2 (replication):
  S1 sends "Withdraw 600" to S2
  S2 sends "Withdraw 700" to S1
  
CONFLICT! Which one is correct?

RESOLUTION: Last-Write-Wins (LWW)

  Withdraw 600 timestamp: 10:00:00.001 (S1)
  Withdraw 700 timestamp: 10:00:00.005 (S2 - later!)
  
  Winner: Withdraw 700 (later timestamp)
  Result: Both servers end at balance = 300
  
  What happened to "Withdraw 600"?
  - Recorded in history (audit trail)
  - Both marked as executed
  - Net effect: One withdrawal is reversed
  - Customer sees: "We processed another withdrawal, final balance = 300"

Why LWW is safe here:
- Both operations recorded (no data loss)
- Deterministic (no flips between servers)
- Timestamps make causality clear
- Audit trail shows what happened
```

## 🔐 Request Idempotency in Detail

### How Idempotency Cache Works

Mobile network example: Customer taps "Withdraw" when signal is weak

```
ATTEMPT 1:
  Client: POST /withdraw with client_reference="mobile_app_ref_001"
  Server processes:
    1. Generate request_id = hash(ref_001) + server_id + timestamp
    2. Check: Is request_id in cache? NO
    3. Process withdrawal: 5000 → 4000
    4. Save in requests table:
       {request_id, response_json, ttl=24hours}
    5. Return: {success: true, balance: 4000}
  
  Network fails before client gets response!

ATTEMPT 2 (5 seconds later, auto-retry):
  Client: POST /withdraw with client_reference="mobile_app_ref_001" (SAME!)
  Server processes:
    1. Generate request_id = same as above
    2. Check: Is request_id in cache? YES! (in requests table)
    3. Return cached response: {success: true, balance: 4000}
    
  Database NOT touched!
  Balance stays at 4000 (not 3000)

ATTEMPT 3 (another retry):
  Same as Attempt 2
  Returns: {success: true, balance: 4000}

RESULT: Charged only once, despite 3 requests!
```

### Why client_reference Matters

```python
# ✓ GOOD - Unique per request
client.withdraw(
    amount=1000,
    client_reference="mobile_app_" + str(uuid4())  # Different each time
)

# ✗ BAD - Same every time!
client.withdraw(
    amount=1000,
    client_reference="withdraw_123"  # Always same!
)
# Second call returns cached response instead of processing new withdrawal!

# ✓ GOOD - Based on user action
client.withdraw(
    amount=1000,
    client_reference="user_" + user_id + "_" + transaction_timestamp
)
```

## 🔒 Pessimistic Locking in Action

### Race Condition Scenario (Without Locking)

```
Account: balance = 1000

THREAD A (at T=1ms):
  1. READ: balance = 1000
  
THREAD B (at T=2ms):
  1. READ: balance = 1000
  
THREAD A (at T=3ms):
  2. COMPUTE: 1000 - 500 = 500
  3. WRITE: balance = 500
  
THREAD B (at T=4ms):
  2. COMPUTE: 1000 - 600 = 400
  3. WRITE: balance = 400
  
RESULT: balance = 400
ACTUAL WITHDRAWN: 500 + 600 = 1100 (OVERDRAFT!)
```

### With Pessimistic Locking

```
Account: balance = 1000
Locks table: empty

THREAD A (at T=1ms):
  1. INSERT into locks (account_id=1, request_id=req_A, timeout=+30sec)
     → Lock acquired (row created)
     
THREAD B (at T=2ms):
  1. TRY INSERT into locks (account_id=1, request_id=req_B, timeout=+30sec)
     → UNIQUE constraint violation!
     → Thread B BLOCKED (waits for lock release)
  
THREAD A (at T=3ms):
  2. SELECT balance (sees 1000)
  3. UPDATE balance = 500
  4. DELETE from locks (release lock)
  
THREAD B (at T=4ms):
  1. Lock acquired! (A's lock deleted)
  2. SELECT balance (sees 500 - the real value!)
  3. Can only withdraw 500, not 600 (insufficient balance check)
  4. Operation fails gracefully
  
RESULT: balance = 500 (correct!)
```

### Lock Timeout Protection

```
If Thread A crashes after acquiring lock:

  1. Lock row created: timestamp = 10:00:00
  2. Thread A crashes
  3. Thread B retries at 10:00:28
  4. Check: is (10:00:28 - 10:00:00) > 30 seconds? NO
  5. Thread B still waits
  6. At 10:00:31, check again: YES, 31 seconds have passed
  7. Lock is stale, delete it
  8. Thread B acquires lock and proceeds

Result: No permanent deadlock, system recovers
```

## 📊 Project Structure

```
mobile-money-simulator/
├── config/
│   ├── settings.py           # Configuration (SERVER_ID, PORT, DB, etc)
│   ├── database.py           # PostgreSQL connection
│   ├── gossip_config.py      # Gossip protocol settings
│   └── __init__.py
│
├── src/
│   ├── models/
│   │   ├── __init__.py
│   │   └── [SQLAlchemy ORM models for Accounts, Transactions, etc]
│   │
│   ├── core/
│   │   ├── operations.py     # Business logic (withdraw, deposit, balance)
│   │   ├── idempotency.py    # Request deduplication cache
│   │   ├── conflict_resolver.py  # Last-Write-Wins strategy
│   │   ├── events.py         # Event sourcing (WITHDRAW, DEPOSIT, etc)
│   │   ├── wal.py            # Write-Ahead Log for durability
│   │   └── quorum.py         # Quorum consensus logic
│   │
│   ├── distributed/
│   │   ├── gossip.py         # Heartbeats, peer discovery
│   │   ├── hashing.py        # Consistent hashing & hash ring
│   │   ├── vector_clock.py   # Causal ordering detection
│   │   ├── replication_manager.py  # Event replication logic
│   │   ├── heartbeat_worker.py    # Background heartbeat sender
│   │   └── __init__.py
│   │
│   ├── ussd/
│   │   ├── protocol.py       # USSD message parsing & formatting
│   │   └── __init__.py
│   │
│   ├── api/
│   │   ├── routes.py         # FastAPI endpoints
│   │   └── __init__.py
│   │
│   └── __init__.py
│
├── client/
│   ├── mobile_money_client.py  # Python SDK for calling servers
│   ├── ussd_phone_client.py    # Simulates feature phone USSD
│   └── [client libraries]
│
├── tests/
│   ├── test_operations.py           # Unit tests for withdraw/deposit
│   ├── test_gossip_replication.py   # P2P sync tests
│   ├── test_3_server_integration.py # Full system tests
│   └── __init__.py
│
├── docker/
│   └── Dockerfile           # Container image
│
├── logs/                    # Application logs
│
├── main.py                  # Entry point (starts server)
├── init_database.py         # Create/migrate DB schema
├── requirements.txt         # Python dependencies
├── docker-compose.yml       # Multi-container orchestration
├── README.md               # This file
└── .env                    # Environment variables (secrets)
```

### Key Components Explained

**config/settings.py**: Loads configuration from environment
- Which server am I? (SERVER_ID)
- What port? (SERVER_PORT)
- Database connection details
- Gossip protocol parameters

**src/core/operations.py**: The business logic
- Validates customer account exists
- Acquires pessimistic lock
- Checks sufficient balance
- Updates balance atomically
- Creates event for replication

**src/distributed/hashing.py**: Route customer → server
- Hash function maps phone_number → position on ring
- Ring has N×150 virtual nodes for balance
- Find nearest server (clockwise)
- Find 2 backup servers for replication

**src/core/wal.py**: Write-Ahead Log for crash recovery
- Before applying transaction, write to WAL disk
- If crash during apply, can replay from WAL
- Ensures no transaction is lost

**src/distributed/gossip.py**: P2P communication
- Heartbeat: "I'm alive, here's my vector clock"
- Event broadcast: "New transaction happened"
- State sync: "You're behind, here are missing events"

## 🧪 Testing

The system includes comprehensive tests:

```bash
# Run all tests
pytest

# Run integration tests (requires 3 servers running)
pytest tests/test_3_server_integration.py -v

# Run with coverage report
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/test_operations.py::test_concurrent_withdrawals -v
```

### Key Test Scenarios

```python
# Test: Idempotency - same request twice = charged once
def test_idempotent_withdrawal():
    # Send request 3 times with same client_reference
    # Expect: First charges, 2nd & 3rd return cached response
    
# Test: Insufficient balance - can't overdraft
def test_insufficient_balance_blocks_withdrawal():
    # Account has 100, try withdraw 200
    # Expect: Fails with "insufficient balance" error
    
# Test: Concurrent operations - locks prevent race conditions
def test_concurrent_withdrawals():
    # Thread A and B both withdraw simultaneously
    # Expect: First succeeds, second blocked, no race condition
    
# Test: Replication - other servers get the transaction
def test_event_replication_to_peers():
    # Withdraw on Server 1
    # Check Server 2 & 3 have same balance
    # Expect: All 3 servers agree
```

## 📊 Understanding the Database Schema

### accounts table
```sql
account_id (PK)
phone_number (UNIQUE)
account_holder_name
balance (DECIMAL - cannot be negative)
status (active/frozen/closed)
created_at
updated_at
```

### transactions table
```sql
transaction_id (PK)
account_id (FK)
operation_type (withdraw/deposit/transfer/fee)
amount (DECIMAL)
balance_before
balance_after
status (pending/completed/failed)
created_at
```

**Why immutable?** Provides audit trail. No UPDATE allowed.

### requests table
```sql
request_id (PK)         -- hash(client_ref + op_type + phone + timestamp)
account_id
response_json           -- Cached response
ttl                     -- Time-to-live (usually 24 hours)
created_at
expires_at
```

**Why track requests?** Idempotency - prevents duplicate charges.

### account_locks table
```sql
account_id (PK)
request_id (FK)         -- Which request acquired this lock
locked_at
timeout                 -- Lock expires (prevents deadlock)
```

**Why pessimistic?** Guarantees no concurrent modifications.

### events table (Event Sourcing)
```sql
event_id (PK)
account_id
event_type (WITHDRAW/DEPOSIT)
amount
timestamp
server_id               -- Which server originated this event
vector_clock            -- JSON: {server_1: 5, server_2: 3, ...}
status (pending/applied/replicated)
replicated_to_servers   -- JSON array of server IDs that ACK'd
```

**Why event sourcing?** Complete history, enables recovery and replication.

## 🔧 Configuration Deep Dive

```bash
# CONCURRENCY
LOCK_TIMEOUT=30           # How long before a stale lock is freed (seconds)
TRANSACTION_TIMEOUT=60    # Max time for operation to complete

# REPLICATION
HEARTBEAT_INTERVAL=5      # Send heartbeat every N seconds
SYNC_INTERVAL=2           # Check for missed events every N seconds
REPLICATION_BATCH_SIZE=10 # Send events in batches of N

# QUORUM
REQUIRED_REPLICAS=2       # Need 2/3 servers to ACK (3 total)

# IDEMPOTENCY
REQUEST_CACHE_TTL=86400   # Cache responses for 24 hours

# HASHING
VIRTUAL_NODES=150         # Each server gets 150 virtual positions on ring
                          # Higher = better load balance, more memory

# USSD
USSD_SESSION_TIMEOUT=180  # Session valid for 3 minutes
USSD_RESPONSE_TIMEOUT=5   # Wait max 5 seconds for response

# LOGGING
LOG_LEVEL=INFO            # DEBUG, INFO, WARNING, ERROR
APP_DEBUG=false           # Enable request/response logging
```

## 🌍 Scaling Considerations

### Horizontal Scaling (Add More Servers)

Adding a 4th server:
```python
servers = {
    "server_1": {"host": "host1", "port": 8001},
    "server_2": {"host": "host2", "port": 8002},
    "server_3": {"host": "host3", "port": 8003},
    "server_4": {"host": "host4", "port": 8004},  # NEW
}
hash_ring = ConsistentHash(servers, virtual_nodes=150)
```

Effects:
- Each phone number automatically routed to nearest server
- Some customers shift from old servers to new server
- Replication continues automatically
- Quorum = 2-3 servers still (depends on design)

### Vertical Scaling (Bigger Hardware)

- Increase `VIRTUAL_NODES` for better load distribution
- Increase `REPLICATION_BATCH_SIZE` for throughput
- Tune PostgreSQL for faster disk I/O

### Database Scaling

For production with millions of customers:
- Use PostgreSQL replication (primary-replica)
- Partition accounts by phone number range
- Read replicas for balance checks (read-only queries)
- Write to primary for transactions

## 🚨 Failure Scenarios & Recovery

### Scenario 1: One Server Crashes

```
Before: S1, S2, S3 all healthy
        Customers: S1 owns 10%, S2 owns 40%, S3 owns 50%

Server S2 crashes (network error):
- Customers calling S2 fail
- Client automatically retries on S1 or S3
- Hash ring shows replicas: use S1 or S3
- After 10 seconds: heartbeat timeout, mark S2 offline
- New requests avoid S2
- All data survives: S1 and S3 have replicated data

When S2 comes back online:
- Heartbeat received from S2
- S2 checks sync_position vs peers
- Missing events downloaded from S1/S3
- Replication log replayed
- S2 returns to healthy state
```

### Scenario 2: Network Partition (S2 isolated)

```
S1 ↔ S3 (connected)
S2   (alone, cannot reach S1/S3)

Transactions come in:
- S1: Can reach S3 (2/3), quorum OK, proceed
- S2: Cannot reach S1/S3 (1/3), quorum FAILED, reject
- S3: Can reach S1 (2/3), quorum OK, proceed

Result:
- S1 & S3 process transactions, agree on state
- S2 rejects (fails safe, no split-brain)
- When partition heals: S2 syncs from S1/S3

This is "split-brain prevention" - better to reject than accept a lie.
```

### Scenario 3: Replication Lag

```
S1: Withdraw on customer at T=0ms
    - Applied to S1 immediately
    - Response sent to customer at T=5ms
    
S2/S3: Receive event at T=50ms (slow network)
    - Apply event
    - Now all 3 agree (eventual consistency)
    
Customer sees: Instant feedback (T=5ms)
System guarantees: Eventual consistency (by T=50ms)
```

## 🐛 Troubleshooting Guide

### Problem: "Address already in use" (Port taken)

```bash
# Find process using port 8001
netstat -ano | findstr :8001

# Kill the process
taskkill /PID <pid> /F

# Or use different port
set SERVER_PORT=8004 && python main.py
```

### Problem: "Connection refused" (Database down)

```bash
# Check PostgreSQL is running
psql -h localhost -U postgres -c "SELECT 1"

# Or start it
pg_ctl -D /usr/local/var/postgres start

# Or with Docker
docker run -d -p 5432:5432 postgres:15
```

### Problem: Locks not releasing (database hanging)

```bash
# Check for stale locks
SELECT * FROM account_locks WHERE locked_at < NOW() - INTERVAL '1 minute';

# Force delete stale locks
DELETE FROM account_locks WHERE locked_at < NOW() - INTERVAL '1 minute';

# Increase timeout if operations are slow
set LOCK_TIMEOUT=60
```

### Problem: Replication not syncing

```bash
# Check gossip connectivity
curl http://localhost:8001/api/v1/peers/status

# Check event log
SELECT COUNT(*) FROM events WHERE status = 'pending';

# Manually trigger sync
curl -X POST http://localhost:8001/api/v1/replication/sync
```

### Problem: High latency on withdraw

```bash
# Check server load
# Enable query logging
set LOG_LEVEL=DEBUG

# Look for slow locks
SELECT account_id, locked_at, timeout 
FROM account_locks 
ORDER BY locked_at DESC;

# Scale up: add more servers
set SERVER_ID=server_4 && python main.py
```

## 📚 References & Further Reading

### Papers
- "Consistent Hashing and Random Trees" (for hash ring)
- "Designing Data-Intensive Applications" (Kleppmann)
- "CALM Consistency" (eventual consistency theory)

### Concepts
- **CAP Theorem**: Can't have Consistency, Availability, Partition-tolerance all at once
- **ACID Properties**: Atomicity, Consistency, Isolation, Durability
- **Vector Clocks**: Detect causality and concurrent events
- **Quorum**: Majority voting for distributed consensus

## 🎯 What This System Teaches

This system demonstrates:
1. **Distributed Consensus**: How servers agree without a master
2. **Fault Tolerance**: Handling failures gracefully
3. **Data Consistency**: Preventing corruption with locks & events
4. **Scalability**: Adding servers without downtime
5. **Real-time Finance**: Building a real payment system safely

Perfect for learning distributed systems while building something realistic!

## 📈 Roadmap (Future Enhancements)

- [ ] **GraphQL API**: Alternative query interface
- [ ] **WebSocket live updates**: Real-time balance notifications
- [ ] **Analytics Dashboard**: Transaction analytics, fraud detection
- [ ] **Multi-currency support**: KES, USD, GBP, etc.
- [ ] **Agent/ATM integration**: Offline cash handling
- [ ] **Card payments**: Visa/Mastercard integration
- [ ] **Blockchain audit trail**: Immutable transaction log
- [ ] **Machine learning**: Fraud detection, anomaly detection
- [ ] **Load testing**: Performance benchmarks at scale

## 📄 License

MIT License - Free to use and modify

## 🤝 Contributing

Contributions welcome! This is a learning project.

```bash
# Fork, create feature branch, test, submit PR
git checkout -b feature/your-feature
pytest
git push origin feature/your-feature
```

## 🙏 Credits

Built to demonstrate real distributed systems principles used in:
- M-Pesa (Kenya's mobile money)
- Remitly
- Square Cash
- Apple Pay
- And millions of payment systems worldwide

---

**Built with ❤️ for African fintech developers**

*Learn distributed systems by building production-ready payment infrastructure*
