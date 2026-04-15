# Distributed Mobile Money System - Architecture Plan (Python)

## 1. SYSTEM OVERVIEW

### Core Components
```
┌─────────────────────────────────────────────────────────────┐
│                      MOBILE CLIENTS                          │
│                    (USSD Feature Phones)                     │
│         *165*2*075346363*1000  (format: code*operation*phone*amount)
└──────────────┬──────────────────┬──────────────────┬─────────┘
               │                  │                  │
        ┌──────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐
        │  Server 1   │    │  Server 2   │    │  Server 3   │
        │(Port 8001)  │◄──►│(Port 8002)  │◄──►│(Port 8003)  │
        └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
               │                  │                  │
        ┌──────▼──────────────────▼──────────────────▼─────────┐
        │           REPLICATED DATABASE (MySQL/PostgreSQL)     │
        │  - Accounts, Transactions, Locks, Replication Log     │
        └────────────────────────────────────────────────────────┘

        Each server has a local copy of the database
        Data is replicated via P2P mechanism
```

---

## 2. KEY ARCHITECTURAL PATTERNS

### 2.1 **Distributed Architecture**
- **P2P (Peer-to-Peer)**: All servers are equal peers, no single master
- **Eventual Consistency**: Changes propagate asynchronously across servers
- **Quorum-based Operations** (optional): For critical operations, require consensus

### 2.2 **Request Flow**
```
1. Client sends USSD code → Server (nearest via hashing)
2. Server parses request → Generate unique request_id (UUID + timestamp)
3. Server processes operation (with pessimistic locking)
4. Server replicates changes to all peers (async)
5. Server sends response to client (sync/async depending on operation)
6. Peer servers eventually receive replication log
```

### 2.3 **Operation Types**

| Operation | Code | Response | Locking | Notes |
|-----------|------|----------|---------|-------|
| **Withdraw** | *165*2* | SYNC (immediate feedback) | Yes (pessimistic) | Requires sufficient balance |
| **Deposit** | *165*1* | ASYNC (callback/SMS) | Yes (pessimistic) | Always succeeds if amount valid |
| **Check Balance** | *165*3* | SYNC (immediate feedback) | No (read-only) | No balance modification |
| **Mini Statement** | *165*4* | ASYNC (callback) | No | Last 10 transactions |

---

## 3. TECHNOLOGY STACK

### Backend Framework
```
Flask / FastAPI
├── API Routes (REST endpoints for servers)
├── USSD Handler (text protocol parser)
├── Request validation & middleware
└── Error handling & logging
```

### Database
```
PostgreSQL (with replication capabilities)
├── Core tables (accounts, transactions, requests, locks)
├── Replication log table
├── Server status tracking
└── Notifications queue
```

### Message Queue (for async operations)
```
Redis or RabbitMQ
├── Notification queue (SMS, callbacks)
├── Replication queue (sync between servers)
└── Request processing queue
```

### Distributed Components
```
Python Libraries:
├── pg8000 or psycopg2 (PostgreSQL)
├── redis-py (Redis caching/queuing)
├── requests (HTTP for P2P calls)
├── pydantic (data validation)
├── APScheduler (scheduled tasks/heartbeat)
├── JWT (request signing/verification)
├── Hashlib (consistent hashing)
└── UUID (unique request IDs)
```

---

## 4. REQUEST ID UNIQUENESS & IDEMPOTENCY

### Request ID Format
```
{server_id}_{timestamp}_{uuid}_{client_reference}
Example: server_1_1712592000_abc123def456_075346363
```

### Idempotency Mechanism
```
1. Client generates request_id (or system generates if missing)
2. Request stored in 'requests' table with status 'received'
3. Server checks if request_id exists (previous execution)
4. If exists: return cached response (idempotent)
5. If new: process and store response
```

### Duplicate Request Handling
```
Request submitted 3 times with SAME request_id:
- First execution: processed, returns {status: success, balance: 4900}
- Second execution: cached response returned instantly
- Third execution: cached response returned instantly
→ Ensures "exactly-once" semantics despite network retries
```

---

## 5. CONSISTENT HASHING FOR SERVER DISCOVERY

### How It Works
```python
# Client-side: Find nearest server for a phone number
request_id = generate_request_id(phone_number)
hash_value = consistent_hash(phone_number)  # CRC32 or SHA1
server = hash_ring.get_node(hash_value)  # Returns server_1, server_2, or server_3

# If primary server unavailable, try next in ring
backup_server = hash_ring.get_next_nodes(hash_value, count=2)
```

### Hash Ring with Virtual Nodes
```
Ring positions (CRC32):
├─ Server_1_v1 → 235921
├─ Server_1_v2 → 567234
├─ Server_1_v3 → 892145
├─ Server_2_v1 → 134567
├─ Server_2_v2 → 456789
...
└─ Server_3_vN → 999234

Phone 075346363 hashes to position 456789 → Routes to Server_2
```

---

## 6. PESSIMISTIC LOCKING

### Lock Acquisition
```python
def acquire_lock(account_id, request_id, server_id, timeout=30):
    """
    Acquires exclusive lock on account
    Returns: (success: bool, lock_id: str, message: str)
    """
    # Check for existing lock
    existing_lock = db.query(AccountLock).filter(
        AccountLock.account_id == account_id,
        AccountLock.expires_at > datetime.now()
    ).first()
    
    if existing_lock:
        return False, None, "Account locked by other operation"
    
    # Acquire new lock
    lock = AccountLock(
        account_id=account_id,
        lock_holder_server=server_id,
        request_id=request_id,
        expires_at=datetime.now() + timedelta(seconds=timeout)
    )
    db.add(lock)
    db.commit()
    return True, lock.lock_id, "Lock acquired"
```

### Lock Release
```python
def release_lock(account_id, request_id):
    """Releases lock after operation completion"""
    db.query(AccountLock).filter(
        AccountLock.account_id == account_id,
        AccountLock.request_id == request_id
    ).delete()
    db.commit()
```

### Deadlock Prevention
```
- Lock timeout: 30 seconds (auto-release if server crashes)
- Lock holder verification: Confirm server is still online
- Watchdog thread: Periodically clean expired locks
```

---

## 7. P2P REPLICATION MECHANISM

### Replication Flow
```
Server_1 processes withdraw transaction
    ↓
Transaction recorded in local 'transactions' table
    ↓
Entry added to 'replication_log' table
    ↓
Async replication worker reads replication_log
    ↓
Send to Server_2 & Server_3 via HTTP POST (with signature)
    ↓
Receiving servers:
    - Verify request signature (HMAC-SHA256)
    - Check version/timestamp to detect duplicates
    - Apply changes to local database
    - Acknowledge with ACK response
    ↓
Source server updates 'replicated_to' field
```

### Replication Log Entry
```python
{
    "replication_id": 12345,
    "operation_type": "insert",  # insert, update, delete
    "table_name": "transactions",
    "record_id": "txn_abc123",
    "data_after": {
        "account_id": 1,
        "amount": 1000,
        "balance_after": 4900,
        "timestamp": "2024-04-08T10:30:00Z"
    },
    "source_server": "server_1",
    "version": 42,
    "timestamp": "2024-04-08T10:30:01Z",
    "signature": "hmac_sha256_signature..."
}
```

### Conflict Resolution
```
Strategy: Last-write-wins with version numbers

Example:
Server_1 processes withdraw at 10:30:00 (version=42)
Server_2 receives & applies at 10:30:05 (version=42)

If messages cross (unlikely but possible):
Server_2 withdraw at 10:30:00 (version=42)
Server_1 withdraw at 10:30:00 (version=42)
→ Compare timestamps: 10:30:00.001 vs 10:30:00.002
→ Apply in order, second transaction fails (insufficient balance)
```

---

## 8. SYNCHRONOUS VS ASYNCHRONOUS OPERATIONS

### Synchronous Operations
```
Operation: Check Balance (read-only)
Flow:
Client → Server: "*165*3*075346363"
Server: Query balance (no lock needed)
Server → Client: "*165*3*075346363*Success*Bal:5000#"
Response time: < 2 seconds
```

### Asynchronous Operations  
```
Operation: Deposit (non-critical timing)
Flow:
Client → Server: "*165*1*075346363*1000"
Server: 
  - Generate request_id
  - Acquire lock
  - Update balance
  - Release lock
  - Return immediate acknowledgment
  - Queue notification: {SMS, Callback, Email}
  
Server → Client: "*165*1*075346363*1000*Received. You will get confirmation SMS#"
Response time: < 1 second

Background Process:
  - Send SMS: "Deposit of 1000 KES successful. New balance: 6000"
  - Replicate to Server_2 and Server_3
  - Update notification status
```

### Critical Synchronous
```
Operation: Withdraw (critical - must have immediate feedback)
Flow:
Client → Server: "*165*2*075346363*1000"
Server:
  1. Generate request_id
  2. Check for duplicate (idempotency)
  3. Acquire lock (wait up to 5 seconds)
  4. Verify balance
  5. Debit account (atomic)
  6. Record transaction
  7. Release lock
  8. Replicate to peers (async in background)
  9. Return response (sync)
  
Server → Client: "*165*2*075346363*1000*Success. New balance: 4900#"
Response time: < 3 seconds

User gets instant feedback on success/failure
Replication happens in background
```

---

## 9. NOTIFICATION SYSTEM

### Notification Types
```
1. Transaction Confirmation (SMS/Push)
   Event: Successful withdraw/deposit
   Trigger: Immediately after operation
   Message: "Withdrawal of KES 1000 successful. Bal: KES 4900"

2. Failed Transaction Alert (SMS)
   Event: Insufficient balance, duplicate request, lock timeout
   Trigger: Immediately
   Message: "Withdrawal of KES 1000 failed. Insufficient balance"

3. Mini Statement (SMS/Callback)
   Event: User requests mini statement
   Trigger: After processing
   Message: Last 10 transactions in batches

4. Server Status Alert (Admin)
   Event: Server goes offline, replication lag > threshold
   Trigger: On detection
   Message: Alert to monitoring system
```

### Notification Queue (Redis/RabbitMQ)
```python
notification_queue = {
    "queue_name": "mobile_notifications",
    "entries": [
        {
            "notification_id": "notif_xyz123",
            "phone_number": "075346363",
            "type": "transaction_confirmation",
            "message": "Withdrawal of KES 1000 successful. Bal: KES 4900",
            "status": "pending",  # pending, sent, failed
            "retry_count": 0,
            "created_at": "2024-04-08T10:30:01Z",
            "delivery_method": "sms"  # sms, push, callback
        }
    ]
}
```

---

## 10. PROJECT STRUCTURE

```
mobile-money-system/
├── config/
│   ├── __init__.py
│   ├── config.py              # Configuration management
│   ├── database.py            # Database setup
│   └── settings.py            # Environment variables
│
├── src/
│   ├── __init__.py
│   ├── models/                # SQLAlchemy ORM models
│   │   ├── account.py
│   │   ├── transaction.py
│   │   ├── request.py
│   │   ├── lock.py
│   │   ├── server.py
│   │   ├── replication_log.py
│   │   └── notification.py
│   │
│   ├── core/                  # Core business logic
│   │   ├── operations.py      # Withdraw, Deposit, Balance
│   │   ├── locking.py         # Pessimistic locking
│   │   ├── idempotency.py     # Request deduplication
│   │   └── hashing.py         # Consistent hashing
│   │
│   ├── distributed/           # P2P & Replication
│   │   ├── replicator.py      # Replication engine
│   │   ├── peer_manager.py    # Peer discovery & health check
│   │   ├── heartbeat.py       # Server heartbeat mechanism
│   │   └── sync_worker.py     # Async replication worker
│   │
│   ├── ussd/                  # USSD Protocol
│   │   ├── parser.py          # Parse USSD codes
│   │   ├── formatter.py       # Format USSD responses
│   │   └── session.py         # USSD session management
│   │
│   ├── api/                   # REST API Endpoints
│   │   ├── routes.py          # Flask/FastAPI routes
│   │   ├── auth.py            # Request signing & verification
│   │   └── middleware.py      # Logging, error handling
│   │
│   ├── notifications/         # Notification Service
│   │   ├── sender.py          # Send SMS/Push/Callback
│   │   ├── queue_worker.py    # Process notification queue
│   │   └── retry_handler.py   # Retry failed notifications
│   │
│   └── utils/                 # Utilities
│       ├── logger.py          # Logging configuration
│       ├── request_id.py      # Generate unique request IDs
│       ├── crypto.py          # Encryption/hashing
│       └── validators.py      # Input validation
│
├── tests/
│   ├── __init__.py
│   ├── test_operations.py     # Unit tests
│   ├── test_replication.py
│   ├── test_locking.py
│   ├── test_integration.py    # Integration tests
│   └── test_distributed.py    # Distributed system tests
│
├── database/
│   ├── migrations/            # Alembic migrations
│   └── schema.sql             # Initial schema
│
├── logs/
│   └── (log files)
│
├── docker-compose.yml         # Multi-container setup
├── requirements.txt           # Python dependencies
├── main.py                    # Application entry point
├── worker.py                  # Background task worker
└── README.md                  # Documentation
```

---

## 11. DEPENDENCIES (requirements.txt)

```
Flask==2.3.2 or FastAPI==0.100.0
SQLAlchemy==2.0.0
psycopg2-binary==2.9.0 or mysql-connector-python
redis==5.0.0
requests==2.31.0
pydantic==2.0.0
python-dotenv==1.0.0
APScheduler==3.10.0
PyJWT==2.8.0
gunicorn==21.0.0
pytest==7.4.0
docker
```

---

## 12. IMPLEMENTATION PHASES

### Phase 1: Core Foundation (Week 1)
- [ ] Set up project structure
- [ ] Database schema & migrations
- [ ] Models & ORM setup
- [ ] Basic Flask/FastAPI app
- [ ] Logging & configuration

### Phase 2: Core Operations (Week 2)
- [ ] Account management
- [ ] Withdraw operation (with locking)
- [ ] Deposit operation
- [ ] Check balance
- [ ] Request idempotency

### Phase 3: Distributed System (Week 3)
- [ ] Consistent hashing
- [ ] P2P replication engine
- [ ] Heartbeat & peer discovery
- [ ] Replication worker (async)
- [ ] Conflict resolution

### Phase 4: USSD & Client API (Week 4)
- [ ] USSD code parser
- [ ] USSD session management
- [ ] Response formatter
- [ ] REST API endpoints
- [ ] Request signing/verification

### Phase 5: Additional Features (Week 5)
- [ ] Notification system
- [ ] Mini statements
- [ ] Transaction history
- [ ] Admin dashboard (optional)
- [ ] Monitoring & alerts

### Phase 6: Testing & Deployment (Week 6)
- [ ] Unit & integration tests
- [ ] Load testing
- [ ] Docker containerization
- [ ] Multi-server setup
- [ ] Documentation

---

## 13. DEPLOYMENT TOPOLOGY

### Local Development (single machine, 3 servers)
```bash
docker-compose up
# Starts:
# - PostgreSQL (shared database)
# - Redis (queue)
# - Server_1 (port 8001)
# - Server_2 (port 8002)
# - Server_3 (port 8003)
# - Replication worker
# - Notification worker
```

### Production (3 separate machines)
```
Machine 1: Server_1 + Local PostgreSQL replica
Machine 2: Server_2 + Local PostgreSQL replica
Machine 3: Server_3 + Local PostgreSQL replica

Central PostgreSQL (or cloud managed DB)
Central Redis (for queues)
Monitoring/Logging stack
```

---

## 14. EXAMPLE USSD FLOWS

### Flow 1: Withdraw 1000 KES
```
Client:  *165*2*075346363*1000#
         (code*operation*account*amount)

Server parses:
{
    "code": 165,
    "operation": "withdraw",
    "account": "075346363",
    "amount": 1000
}

Server response: *165*2*Success*NewBal:4900#
```

### Flow 2: Check Balance
```
Client:  *165*3*075346363#

Server response: *165*3*Balance:5900#
```

### Flow 3: Deposit 500 KES
```
Client:  *165*1*075346363*500#

Server response: *165*1*DepositReceived.SMS confirmation sent#

Background: SMS sent after 1-2 seconds
"Deposit of 500 KES successful. New balance: 6400"
```

---

## QUESTIONS FOR CLARIFICATION

1. **Database**: PostgreSQL (recommended) or MySQL?
2. **Message Queue**: Redis or RabbitMQ?
3. **Framework**: Flask (simpler) or FastAPI (modern)?
4. **Authentication**: API keys, JWT, or Signatures?
5. **Monitoring**: Prometheus + Grafana, or simple logging?
6. **Deployment**: Docker Compose locally, or separate machines?

---

Let me know if this plan looks good or if you'd like me to adjust anything before we start implementation!
