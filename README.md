# Mobile Money System - Distributed P2P Payment Platform

A production-ready distributed mobile money system built with Python, FastAPI, and PostgreSQL. Implements a peer-to-peer architecture with consistent hashing for server discovery, pessimistic locking for concurrency control, and eventual consistency replication.

## 📋 Features

- **Distributed P2P Architecture**: Multiple equal-peer servers for high availability
- **Consistent Hashing**: Route clients to optimal server based on phone number
- **Pessimistic Locking**: Prevent race conditions in concurrent operations
- **Request Idempotency**: Exactly-once semantics with unique request IDs
- **USSD Protocol Support**: Feature phone accessibility
- **Operations**: Withdraw, Deposit, Check Balance, Mini Statement
- **Async Notifications**: SMS confirmations for transactions
- **P2P Replication**: Eventual consistency across servers
- **Automatic Failover**: Clients retry on alternate servers

## 🏗️ Architecture

```
        CLIENTS (USSD/API)
             ↓
    ┌────────┼────────┐
    ↓        ↓        ↓
 Server_1  Server_2  Server_3
 (8001)    (8002)    (8003)
    │        │        │
    └────────┼────────┘
             ↓
      PostgreSQL Database
         (Shared)
             ↓
    ┌───────────────────┐
    │  Replication Log  │
    │  - Insert/Update  │
    │  - P2P Sync       │
    └───────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 12+
- Redis 7+
- Docker & Docker Compose (optional)

### Installation

1. **Clone & Setup**
```bash
cd "mobile money system"
pip install -r requirements.txt
cp .env.example .env
```

2. **Initialize Database**
```bash
# Create database
createdb mobile_money_system

# OR use Docker
docker-compose up -d postgres
```

3. **Start Servers**

**Option A: Docker Compose (Recommended)**
```bash
docker-compose up
# This starts all 3 servers + PostgreSQL + Redis
```

**Option B: Manual (Single Machine, Multiple Ports)**
```bash
# Terminal 1 - Server 1 (Port 8001)
export SERVER_ID=server_1 && export SERVER_PORT=8001 && python main.py

# Terminal 2 - Server 2 (Port 8002)
export SERVER_ID=server_2 && export SERVER_PORT=8002 && python main.py

# Terminal 3 - Server 3 (Port 8003)
export SERVER_ID=server_3 && export SERVER_PORT=8003 && python main.py
```

### Verify Installation

```bash
# Check server health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health

# Check hash ring status
curl http://localhost:8001/api/v1/hash-ring/status
```

## 💳 Usage Examples

### Python Client

```python
from client.mobile_money_client import MobileMoneyClient

# Initialize client
client = MobileMoneyClient(
    server_urls=[
        "http://localhost:8001",
        "http://localhost:8002",
        "http://localhost:8003"
    ]
)

# Create account
success, response = client.create_account(
    phone_number="075346363",
    account_holder_name="John Doe",
    initial_balance=10000.0
)
print(response)

# Withdraw
success, response = client.withdraw(
    account_id=1,
    phone_number="075346363",
    amount=1000.0
)
print(f"Withdraw: {response}")

# Check balance
success, response = client.check_balance(account_id=1)
print(f"Balance: {response['data']['balance']}")

# Deposit
success, response = client.deposit(
    account_id=1,
    phone_number="075346363",
    amount=500.0
)
print(f"Deposit: {response}")
```

### USSD Requests

Format: `*165*operation*phone*[amount]`

**Withdraw 1000 KES:**
```
*165*2*075346363*1000#
```

**Deposit 500 KES:**
```
*165*1*075346363*500#
```

**Check Balance:**
```
*165*3*075346363#
```

**Mini Statement:**
```
*165*4*075346363#
```

**Using Client:**
```python
success, response = client.ussd_request("*165*2*075346363*1000#")
print(response['ussd_response'])
# Output: *165*2*Success*NewBal:9000#
```

### REST API

**Create Account:**
```bash
curl -X POST http://localhost:8001/api/v1/account/create \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "075346363",
    "account_holder_name": "John Doe",
    "initial_balance": 10000.0
  }'
```

**Withdraw:**
```bash
curl -X POST http://localhost:8001/api/v1/operation/withdraw \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "phone_number": "075346363",
    "amount": 1000.0
  }'
```

**Check Balance:**
```bash
curl -X POST http://localhost:8001/api/v1/operation/balance \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "client_ip": "127.0.0.1"
  }'
```

**USSD Gateway:**
```bash
curl -X POST http://localhost:8001/api/v1/ussd \
  -H "Content-Type: application/json" \
  -d '{
    "ussd_input": "*165*2*075346363*1000#"
  }'
```

**Server Discovery:**
```bash
curl http://localhost:8001/api/v1/routing/discover/075346363
```

## 🌐 Routing & Server Discovery

### Consistent Hashing

Clients are routed to servers based on their phone number using a hash ring:

```python
from src.distributed.hashing import ConsistentHash, ServerDiscovery

# Initialize hash ring
servers = {
    "server_1": {"host": "localhost", "port": 8001},
    "server_2": {"host": "localhost", "port": 8002},
    "server_3": {"host": "localhost", "port": 8003},
}
hash_ring = ConsistentHash(servers, virtual_nodes=150)
discovery = ServerDiscovery(hash_ring)

# Route request
routing = discovery.route_request("075346363")
print(routing['primary_server'])
# Output: {'id': 'server_2', 'url': 'http://localhost:8002'}

# Get replicas for failover
replicas = discovery.find_replica_servers("075346363")
print(replicas)  # [server_1, server_3]
```

### Phone → Server Mapping

- **075346363** → server_2 (primary) → [server_1, server_3] (replicas)
- **0721234567** → server_1 (primary) → [server_2, server_3] (replicas)
- **0728765432** → server_3 (primary) → [server_2, server_1] (replicas)

## 🔐 Request Idempotency

All requests receive a unique ID to prevent duplicate charges:

```python
request_id = RequestIdempotency.generate_request_id(
    phone_number="075346363",
    operation_type="withdraw",
    client_reference="ref_123"
)
# Output: server_1_1712592000123_abc123_075346363

# Submit request 3 times - only charged once!
for i in range(3):
    client.withdraw(account_id=1, phone_number="075346363", amount=1000)
    # First: processed, returns balance 9000
    # Second: cached response, returns balance 9000
    # Third: cached response, returns balance 9000
```

## 🔒 Pessimistic Locking

Accounts are locked during operations to prevent race conditions:

```python
# Server acquires lock
lock_acquired = AccountOperations.acquire_lock(
    db=db_session,
    account_id=1,
    request_id="req_123",
    timeout=30  # Lock expires after 30 seconds
)

if lock_acquired:
    # Perform operation (withdraw/deposit)
    # Lock is exclusively held
    pass
finally:
    # Release lock after operation
    AccountOperations.release_lock(db, account_id=1, request_id="req_123")
```

## 📊 Operations

### Withdraw (Synchronous - Critical)
```
Request → Server:
  1. Generate request_id
  2. Check duplicate (idempotency)
  3. Acquire lock (30 seconds)
  4. Verify balance
  5. Debit account (atomic)
  6. Record transaction
  7. Release lock
  
Response time: < 3 seconds
Feedback: Immediate
Replication: Background async
```

### Deposit (Sync Operation, Async Notification)
```
Request → Server:
  1. Generate request_id
  2. Check duplicate
  3. Acquire lock
  4. Credit account
  5. Record transaction
  6. Release lock
  7. Queue SMS notification (async)
  
Response time: < 2 seconds
Feedback: Immediate acknowledgment
Notification: SMS within 1-2 minutes
```

### Check Balance (Read-Only - No Locking)
```
Request → Server:
  1. Read account balance
  
Response time: < 1 second
Feedback: Immediate
No locking needed
```

## 🔄 P2P Replication

Data automatically replicates across servers:

```
Server_1 executes transaction
    ↓
Entry added to replication_log
    ↓
Async worker reads log
    ↓
HTTP POST to Server_2 & Server_3 (with HMAC signature)
    ↓
Receiving servers verify signature and apply changes
    ↓
Acknowledges successful replication
```

## 📦 Project Structure

```
mobile-money-system/
├── config/                      # Configuration
│   ├── settings.py             # Environment-based config
│   └── database.py             # DB connection
├── src/
│   ├── models/                 # SQLAlchemy ORM models
│   ├── core/                   # Business logic
│   │   ├── operations.py       # Withdraw/Deposit/Balance
│   │   ├── idempotency.py      # Request deduplication
│   │   └── hashing.py          # Consistent hashing
│   ├── distributed/            # P2P & Replication
│   │   ├── replicator.py       # Replication engine
│   │   └── hashing.py          # Hash ring
│   ├── ussd/                   # USSD protocol
│   │   └── protocol.py         # Parser & formatter
│   ├── api/                    # FastAPI routes
│   │   └── routes.py           # API endpoints
│   └── notifications/          # Notification system
├── client/                     # Client library
│   └── mobile_money_client.py  # Python client RPC
├── database/                   # Database files
├── docker/                     # Docker files
├── tests/                      # Test suite
├── logs/                       # Application logs
├── main.py                     # Application entry point
├── requirements.txt            # Python dependencies
└── docker-compose.yml          # Multi-container setup
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_operations.py

# Run with coverage
pytest --cov=src tests/
```

## 📝 Database Schema

### Core Tables
- **accounts**: User accounts with balance
- **transactions**: Immutable transaction log
- **requests**: Request tracking for idempotency
- **account_locks**: Pessimistic locking

### Distributed
- **replication_log**: P2P sync log
- **server_status**: Peer health status
- **ussd_sessions**: Session management

### Notifications
- **notifications**: SMS/callback queue
- **audit_log**: Audit trail

## 🔧 Configuration

### Environment Variables
```bash
# Server
SERVER_ID=server_1
SERVER_PORT=8001

# Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres

# Operations
LOCK_TIMEOUT=30
TRANSACTION_TIMEOUT=60

# Replication
REPLICATION_ENABLED=true
HEARTBEAT_INTERVAL=10
SYNC_INTERVAL=5

# Security
REQUEST_SIGNING_KEY=your-secret-key

# USSD
USSD_SESSION_TIMEOUT=180

# Notifications
ASYNC_NOTIFICATION_ENABLED=true
```

## 📊 Monitoring

### Health Endpoints
```bash
GET /health                    # Simple health check
GET /status                    # Detailed server status
GET /api/v1/hash-ring/status  # Hash ring configuration
```

### Logs
```bash
tail -f logs/server.log
```

### Metrics (TODO)
- Request latency
- Transaction success rate
- Replication lag
- Server availability

## 🚨 Error Handling

All operations return structured responses:

```json
{
  "status": "success|error",
  "message": "Operation description",
  "data": {
    "transaction_id": 123,
    "balance_after": 9000,
    "timestamp": "2024-04-08T10:30:00Z"
  },
  "request_id": "server_1_1712592000_abc123_075346363"
}
```

## 🔒 Security

- **Request Signing**: HMAC-SHA256 signatures
- **Unique Request IDs**: Prevent replay attacks
- **Timeout Protection**: Lock timeouts prevent deadlocks
- **IP Tracking**: Client IP logged for audit
- **Status Validation**: Account status checks

## 🎯 Production Deployment

### Multi-Machine Setup
```
Machine 1: Server_1 + PostgreSQL Replica
Machine 2: Server_2 + PostgreSQL Replica
Machine 3: Server_3 + PostgreSQL Replica

Central PostgreSQL (Primary)
Central Redis (Queue)
Monitoring Stack (Prometheus + Grafana)
```

### Scaling
Add more servers:
```python
servers = {
    "server_1": {"host": "host1", "port": 8001},
    "server_2": {"host": "host2", "port": 8002},
    "server_3": {"host": "host3", "port": 8003},
    "server_4": {"host": "host4", "port": 8001},  # Add new server
    # ... more servers
}
hash_ring = ConsistentHash(servers, virtual_nodes=150)
```

## 📚 API Documentation

Auto-generated Swagger docs available at:
```
http://localhost:8001/docs
http://localhost:8002/docs
http://localhost:8003/docs
```

## 🐛 Troubleshooting

### Port Already in Use
```bash
netstat -ano | grep 8001  # Find process using port
taskkill /PID <pid> /F    # Kill process
```

### Database Connection Issues
```bash
# Test PostgreSQL connection
psql -h localhost -U postgres -d mobile_money_system

# Check connection string
echo $DATABASE_URL
```

### Lock Timeout
Increase `LOCK_TIMEOUT` if operations take too long:
```bash
export LOCK_TIMEOUT=60
```

## 📞 Support

For issues, enable debug logging:
```bash
export LOG_LEVEL=DEBUG
export APP_DEBUG=true
```

## 📄 License

MIT License

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create feature branch
3. Add tests
4. Submit pull request

## 📈 Roadmap

- [ ] GraphQL API
- [ ] WebSocket live updates
- [ ] Advanced analytics dashboard
- [ ] Multi-currency support
- [ ] Agent/ATM integration
- [ ] Card payments
- [ ] Blockchain audit trail

---

**Built with ❤️ for African mobile money markets**
