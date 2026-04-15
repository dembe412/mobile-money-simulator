# P2P MULTI-COMPUTER DEPLOYMENT GUIDE

## Running Mobile Money System Across Multiple Machines - P2P Architecture

**Scenario:** Multiple computers on same LAN acting as **equal peers** - **NO central point of failure**

---

## 🏗️ ARCHITECTURE OVERVIEW

### Key Principle: ALL SERVERS ARE EQUAL

```
              LOCAL NETWORK (192.168.1.0/24)
  
     Computer A          Computer B          Computer C
     (192.168.1.10)      (192.168.1.11)      (192.168.1.12)
            │                   │                    │
     ┌──────────────┐  ┌──────────────┐   ┌──────────────┐
     │  FastAPI     │  │  FastAPI     │   │  FastAPI     │
     │  Server 1    │  │  Server 2    │   │  Server 3    │
     │  Port 8001   │  │  Port 8002   │   │  Port 8003   │
     └──────────────┘  └──────────────┘   └──────────────┘
            │                   │                    │
     ┌──────────────┐  ┌──────────────┐   ┌──────────────┐
     │ PostgreSQL   │  │ PostgreSQL   │   │ PostgreSQL   │
     │ (local DB)   │  │ (local DB)   │   │ (local DB)   │
     └──────────────┘  └──────────────┘   └──────────────┘
            │                   │                    │
     ┌──────────────┐  ┌──────────────┐   ┌──────────────┐
     │ Redis        │  │ Redis        │   │ Redis        │
     │ (local)      │  │ (local)      │   │ (local)      │
     └──────────────┘  └──────────────┘   └──────────────┘
            │                   │                    │
            └───────────────────┼────────────────────┘
                    P2P Replication
                 (peer-to-peer sync)
                 Background jobs sync
                 transactions to peers
```

### Why P2P Architecture?

| Feature | Benefit |
|---------|---------|
| **No central point** | Any server can go down, others keep working |
| **Fault tolerance** | 2 of 3 servers = 66% uptime (vs 0% with central DB) |
| **Data locality** | Local DB = faster transactions |
| **Simple scaling** | Add servers = just add peers, no DB migration |
| **All equal** | No master/slave complexity |

---

## NETWORK SETUP

### Requirements

- ✅ All computers on same Wi-Fi or Ethernet network
- ✅ Can ping each other: `ping 192.168.1.11`
- ✅ Firewall allows ports: 8001, 8002, 8003
- ✅ Static IP addresses recommended (or DHCP reservations)

### Computer Configuration

| Computer | Role | Server ID | Port | Example IP |
|----------|------|-----------|------|-----------|
| A | App + DB + Cache | server_1 | 8001 | 192.168.1.10 |
| B | App + DB + Cache | server_2 | 8002 | 192.168.1.11 |
| C | App + DB + Cache | server_3 | 8003 | 192.168.1.12 |

**Each computer has everything it needs - INDEPENDENT!**

---

## STEP 1: IDENTIFY YOUR COMPUTERS

### Find IP Addresses

**Windows (all 3 computers):**
```powershell
ipconfig
```
Look for IPv4 Address (e.g., 192.168.1.10)

**Linux/Mac:**
```bash
ifconfig | grep "inet "
```

**Write them down:**
```
Computer A IP: 192.168.1.10
Computer B IP: 192.168.1.11
Computer C IP: 192.168.1.12
```

### Test Network Connectivity

From each computer, verify it can reach the others:
```bash
# From Computer A
ping 192.168.1.11
ping 192.168.1.12

# From Computer B
ping 192.168.1.10
ping 192.168.1.12

# From Computer C
ping 192.168.1.10
ping 192.168.1.11
```

All should show "Reply from..." - if not, fix network first!

---

## STEP 2: INSTALL DEPENDENCIES ON EACH COMPUTER

Each computer needs PostgreSQL, Redis, and Python.

### Computer A (192.168.1.10)

**Install PostgreSQL locally:**
- Download: https://www.postgresql.org/download/windows/
- Or on Linux: `sudo apt-get install postgresql postgresql-contrib`
- Password: `secure_pwd` (change in production!)

**Install Redis locally:**
- Windows: https://github.com/microsoftarchive/redis/releases
- Or on Linux: `sudo apt-get install redis-server`

**Verify services are running:**
```bash
# Test PostgreSQL (should return version)
psql --version

# Test Redis (should return PONG)
redis-cli ping
```

**Create database:**
```bash
psql -U postgres
```
Then in psql:
```sql
CREATE DATABASE mobile_money_system;
\q
```

### Repeat for Computer B and Computer C

Do the same installation steps for 192.168.1.11 and 192.168.1.12

---

## STEP 3: COPY PROJECT TO EACH COMPUTER

On each of the 3 computers:

```bash
# Create folder
mkdir mobile_money_system
cd mobile_money_system

# Copy project files (via git, zip, or rsync)
# Either:
git clone <your-repo-url> .

# Or copy files manually (all Python source files, requirements.txt, etc.)
```

Verify files are there:
```bash
ls -la
# Should see: config/, src/, client/, main.py, requirements.txt, etc.
```

---

## STEP 4: INSTALL PYTHON DEPENDENCIES

On **each computer**:

```bash
pip install -r requirements.txt
```

Or for specific environments:
```bash
python -m pip install -r requirements.txt
```

---

## STEP 5: CREATE .ENV FILES

### On Computer A (192.168.1.10)

Create file: `.env`

```bash
# ═══════════════════════════════════════════════════════
# COMPUTER A Configuration (192.168.1.10)
# ═══════════════════════════════════════════════════════

# Server Identity
SERVER_ID=server_1
SERVER_NAME=Mobile Money Server 1
SERVER_HOST=0.0.0.0
SERVER_PORT=8001

# Database (LOCAL - not remote!)
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=secure_pwd
DB_NAME=mobile_money_system

# Redis (LOCAL)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# === P2P CONFIGURATION ===
# List OTHER servers (not yourself!)
# Format: http://ip:port,http://ip:port
PEER_SERVERS=http://192.168.1.11:8002,http://192.168.1.12:8003

# Replication (P2P settings)
REPLICATION_ENABLED=true
REPLICATION_INTERVAL=5
REPLICATION_TIMEOUT=10
REPLICATION_RETRY_COUNT=3
HEARTBEAT_INTERVAL=10
SYNC_INTERVAL=5

# Hash algorithm for consistent hashing
HASH_VIRTUAL_NODES=150
HASH_ALGORITHM=crc32

# ═══════════════════════════════════════════════════════
# Operation settings
LOCK_TIMEOUT=30
TRANSACTION_TIMEOUT=60
OPERATION_RETRY_COUNT=3
OPERATION_RETRY_DELAY=1000

# Security
REQUEST_SIGNING_KEY=change-this-in-production-server1

# Logging
LOG_LEVEL=INFO
APP_ENV=development
```

### On Computer B (192.168.1.11)

Create file: `.env`

```bash
# ═══════════════════════════════════════════════════════
# COMPUTER B Configuration (192.168.1.11)
# ═══════════════════════════════════════════════════════

SERVER_ID=server_2
SERVER_NAME=Mobile Money Server 2
SERVER_HOST=0.0.0.0
SERVER_PORT=8002

# Database (LOCAL)
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=secure_pwd
DB_NAME=mobile_money_system

# Redis (LOCAL)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# === P2P CONFIGURATION ===
# List OTHER servers (not yourself!)
PEER_SERVERS=http://192.168.1.10:8001,http://192.168.1.12:8003

REPLICATION_ENABLED=true
REPLICATION_INTERVAL=5
REPLICATION_TIMEOUT=10
REPLICATION_RETRY_COUNT=3
HEARTBEAT_INTERVAL=10
SYNC_INTERVAL=5

HASH_VIRTUAL_NODES=150
HASH_ALGORITHM=crc32

LOCK_TIMEOUT=30
TRANSACTION_TIMEOUT=60
OPERATION_RETRY_COUNT=3
OPERATION_RETRY_DELAY=1000

REQUEST_SIGNING_KEY=change-this-in-production-server2

LOG_LEVEL=INFO
APP_ENV=development
```

### On Computer C (192.168.1.12)

Create file: `.env`

```bash
# ═══════════════════════════════════════════════════════
# COMPUTER C Configuration (192.168.1.12)
# ═══════════════════════════════════════════════════════

SERVER_ID=server_3
SERVER_NAME=Mobile Money Server 3
SERVER_HOST=0.0.0.0
SERVER_PORT=8003

# Database (LOCAL)
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=secure_pwd
DB_NAME=mobile_money_system

# Redis (LOCAL)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# === P2P CONFIGURATION ===
# List OTHER servers (not yourself!)
PEER_SERVERS=http://192.168.1.10:8001,http://192.168.1.11:8002

REPLICATION_ENABLED=true
REPLICATION_INTERVAL=5
REPLICATION_TIMEOUT=10
REPLICATION_RETRY_COUNT=3
HEARTBEAT_INTERVAL=10
SYNC_INTERVAL=5

HASH_VIRTUAL_NODES=150
HASH_ALGORITHM=crc32

LOCK_TIMEOUT=30
TRANSACTION_TIMEOUT=60
OPERATION_RETRY_COUNT=3
OPERATION_RETRY_DELAY=1000

REQUEST_SIGNING_KEY=change-this-in-production-server3

LOG_LEVEL=INFO
APP_ENV=development
```

---

## STEP 6: INITIALIZE DATABASES

On **each computer**, create the database schema:

```bash
# Run migrations (assumes you have a migration script)
python -m alembic upgrade head

# Or manually via psql
psql -U postgres -d mobile_money_system < schema.sql
```

**Verify database created:**
```bash
psql -U postgres -d mobile_money_system -c "\dt"
```

Should show tables: account, transaction, replication_log_entry, etc.

---

## STEP 7: START ALL SERVERS

### On Computer A

```bash
python main.py
# Should show: "Uvicorn running on http://0.0.0.0:8001"
```

### On Computer B (in separate terminal)

```bash
python main.py
# Should show: "Uvicorn running on http://0.0.0.0:8002"
```

### On Computer C (in separate terminal)

```bash
python main.py
# Should show: "Uvicorn running on http://0.0.0.0:8003"
```

---

## STEP 8: VERIFY ALL SERVERS RUNNING

From **any computer**, test all 3 servers:

```bash
# Test from Computer A
curl http://192.168.1.10:8001/health
curl http://192.168.1.11:8002/health
curl http://192.168.1.12:8003/health

# All should return:
# {"status": "healthy"}
```

If any fails, check:
- Is server running? (check terminal output)
- Is firewall blocking port? (open ports 8001-8003)
- Wrong IP address? (verify with ipconfig)

---

## STEP 9: TEST P2P REPLICATION

### Scenario 1: Deposit on Server A, Check on Server B

**Terminal 1 - New account on Server A:**
```bash
python client/ussd_phone_client.py --phone 0754300000 --server http://192.168.1.10:8001
```

In menu:
1. Deposit
2. Amount: 10000
3. Transaction should succeed

**Terminal 2 - Check balance on Server B:**
```bash
python client/ussd_phone_client.py --phone 0754300000 --server http://192.168.1.11:8002
```

In menu:
1. Check balance
2. Should show: **10000** ✅ (replicated from Server A!)

### Scenario 2: Stop One Server, Others Continue

```bash
# Stop Server A (press Ctrl+C in its terminal)

# Can still use Server B and C
python client/ussd_phone_client.py --phone 0754300000 --server http://192.168.1.11:8002
# Withdraw 3000 → should work ✅

# Can still use Server C
python client/ussd_phone_client.py --phone 0754300000 --server http://192.168.1.12:8003
# Check balance → should show 7000 ✅
```

### Scenario 3: Restart Offline Server, Auto-Sync

```bash
# Restart Server A (was stopped in Scenario 2)
# On Computer A: python main.py

# Wait 10 seconds for replication to catch up
# Then check:
python client/ussd_phone_client.py --phone 0754300000 --server http://192.168.1.10:8001
# Check balance → should show 7000 ✅ (synced!)
```

---

## MONITORING & TROUBLESHOOTING

### View Replication Status

```bash
# On any computer with psql
psql -U postgres -d mobile_money_system -c "SELECT * FROM replication_log_entry ORDER BY created_at DESC LIMIT 10;"
```

Shows which updates were replicated to which peers.

### Check Peer Connectivity

```bash
# From Server A, see which peers it knows about
curl http://192.168.1.10:8001/peers
```

Response should show:
```json
{
  "healthy_peers": [
    "http://192.168.1.11:8002",
    "http://192.168.1.12:8003"
  ]
}
```

### Common Issues

**Issue: "Cannot connect to database"**
```bash
# Check PostgreSQL is running
psql -U postgres

# Check DB_HOST in .env = localhost
```

**Issue: "Cannot reach peer server"**
```bash
# Check peer URL format in PEER_SERVERS
# Should be: http://192.168.1.11:8002 (no trailing slash)

# Test connectivity:
curl http://192.168.1.11:8002/health
```

**Issue: "Data not replicating"**
```bash
# Check REPLICATION_ENABLED=true in .env
grep "REPLICATION_ENABLED" .env

# Check logs for replication errors
tail -f logs/server.log | grep replication
```

**Issue: "Port already in use"**
```bash
# Check what's using the port
netstat -ano | findstr 8001

# Kill it or change SERVER_PORT in .env
```

---

## PRODUCTION CHECKLIST

- [ ] Change all `REQUEST_SIGNING_KEY` values (unique per server)
- [ ] Change `DB_PASSWORD` from `secure_pwd` to strong password
- [ ] Set `APP_ENV=production`
- [ ] Enable HTTPS (configure nginx reverse proxy)
- [ ] Setup automated backups of each database
- [ ] Configure monitoring (check /health endpoint regularly)
- [ ] Set firewall rules (only allow necessary ports)
- [ ] Use static IP addresses (not DHCP)
- [ ] Implement monitoring & alerting
- [ ] Document your network IPs and access procedures

---

## SCALING TO MORE SERVERS

Need 5 servers instead of 3? Simple!

1. Copy project to server #4 (192.168.1.13:8004)
2. Create .env with:
   - `SERVER_ID=server_4`
   - `SERVER_PORT=8004`
   - `PEER_SERVERS=http://192.168.1.10:8001,http://192.168.1.11:8002,http://192.168.1.12:8003`
3. Run: `python main.py`
4. Update other servers' .env files to add new peer
5. Restart all servers

**That's it!** P2P scales horizontally!

---

## BACKUP & DISASTER RECOVERY

### Daily Backup (Each Server)

```bash
# Backup each server's local database
pg_dump -U postgres mobile_money_system > backup_server1_$(date +%Y%m%d).sql

# Store on external drive or cloud
```

### Restore from Backup

```bash
# If Server A failed completely
# Get backup of latest successful state
psql -U postgres mobile_money_system < backup_server1_20240115.sql

# Restart server
python main.py

# Replication worker will sync any missed transactions
```

---

## DOCUMENTATION REFERENCES

- **QUICK_REFERENCE_MULTI_COMPUTER.md** - 5-minute quick start
- **P2P_DISTRIBUTED_DEPLOYMENT.md** - This file (detailed guide)
- **DEPLOYMENT_REPORT.md** - Full system report
- **README.md** - System overview

---

**Remember:** All servers are equals. There is NO single point of failure. This is true distributed computing! 🎉
