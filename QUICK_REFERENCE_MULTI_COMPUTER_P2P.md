# MULTI-COMPUTER SETUP - QUICK REFERENCE (P2P ARCHITECTURE)

**Your Scenario:** Multiple computers (A, B, C) on same local network - **ALL peers, NO central point**

---

## 🚀 QUICK START (5 STEPS)

### STEP 1: Identify Your Computers
```
Computer A: server_1    IP: 192.168.1.10   Port: 8001
Computer B: server_2    IP: 192.168.1.11   Port: 8002
Computer C: server_3    IP: 192.168.1.12   Port: 8003
```

> **Find your IP:** `ipconfig` (Windows) or `ifconfig` (Linux)

### STEP 2: Prepare Each Computer (ALL 3 are equal!)

**Each computer needs its OWN:**
- ✅ PostgreSQL database (local)
- ✅ Redis cache (local)
- ✅ FastAPI server running
- ✅ Peer list (other 2 servers' URLs)

### STEP 3: Setup Server A (192.168.1.10)

**Create `.env` file:**
```bash
# Server Identity
SERVER_ID=server_1
SERVER_PORT=8001
SERVER_HOST=0.0.0.0

# Local Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=secure_pwd
DB_NAME=mobile_money_system

# Local Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Peer servers (list OTHER servers, not itself!)
PEER_SERVERS=http://192.168.1.11:8002,http://192.168.1.12:8003

# Replication settings
REPLICATION_ENABLED=true
REPLICATION_INTERVAL=5
REPLICATION_TIMEOUT=10
```

**Install and start:**
```bash
# Install PostgreSQL locally
# Create database: CREATE DATABASE mobile_money_system;

# Install Redis locally
# Start Redis

# Run the system
pip install -r requirements.txt
python main.py
```

### STEP 4: Setup Server B (192.168.1.11)

**Create `.env` file:**
```bash
SERVER_ID=server_2
SERVER_PORT=8002
SERVER_HOST=0.0.0.0

DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=secure_pwd
DB_NAME=mobile_money_system

REDIS_HOST=localhost
REDIS_PORT=6379

# Peer servers (list OTHER servers)
PEER_SERVERS=http://192.168.1.10:8001,http://192.168.1.12:8003

REPLICATION_ENABLED=true
REPLICATION_INTERVAL=5
REPLICATION_TIMEOUT=10

python main.py
```

### STEP 5: Setup Server C (192.168.1.12)

**Create `.env` file:**
```bash
SERVER_ID=server_3
SERVER_PORT=8003
SERVER_HOST=0.0.0.0

DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=secure_pwd
DB_NAME=mobile_money_system

REDIS_HOST=localhost
REDIS_PORT=6379

# Peer servers (list OTHER servers)
PEER_SERVERS=http://192.168.1.10:8001,http://192.168.1.11:8002

REPLICATION_ENABLED=true
REPLICATION_INTERVAL=5
REPLICATION_TIMEOUT=10

python main.py
```

---

## ✅ VERIFY ALL SERVERS RUNNING

Test from any computer:
```bash
# Check all servers are up
curl http://192.168.1.10:8001/health
curl http://192.168.1.11:8002/health
curl http://192.168.1.12:8003/health

# All should return: {"status": "healthy"}
```

---

## 📋 PRE-DEPLOYMENT CHECKLIST

**Network:**
- [ ] All 3 computers on same network (WiFi or Ethernet)
- [ ] Computers can ping each other
- [ ] No firewalls blocking ports 8001, 8002, 8003

**On Each Computer:**
- [ ] PostgreSQL installed and running locally
- [ ] Redis installed and running locally
- [ ] Database created: `CREATE DATABASE mobile_money_system;`
- [ ] Python 3.10+ installed
- [ ] Project files copied to each computer
- [ ] `.env` file created with PEER_SERVERS list
- [ ] Dependencies installed: `pip install -r requirements.txt`

**Peer Configuration:**
- [ ] Each server lists OTHER servers, not itself
- [ ] Server A: PEER_SERVERS = B,C (not A)
- [ ] Server B: PEER_SERVERS = A,C (not B)
- [ ] Server C: PEER_SERVERS = A,B (not C)

---

## 🔗 ARCHITECTURE DIAGRAM (P2P Structure)

```
┌───────────────────────────────────────────────────────────┐
│              LOCAL NETWORK (192.168.1.0/24)              │
└───────────────────────────────────────────────────────────┘

    Server A              Server B              Server C
    (192.168.1.10)        (192.168.1.11)        (192.168.1.12)
    Port 8001             Port 8002              Port 8003
    
    ┌──────────────┐     ┌──────────────┐      ┌──────────────┐
    │ FastAPI      │     │ FastAPI      │      │ FastAPI      │
    │ Server 1     │     │ Server 2     │      │ Server 3     │
    └──────────────┘     └──────────────┘      └──────────────┘
           ▲                    ▲                      ▲
           │                    │                      │
    ┌──────────────┐     ┌──────────────┐      ┌──────────────┐
    │ PostgreSQL   │     │ PostgreSQL   │      │ PostgreSQL   │
    │ +            │     │ +            │      │ +            │
    │ Redis        │     │ Redis        │      │ Redis        │
    └──────────────┘     └──────────────┘      └──────────────┘
           ▲                    ▲                      ▲
           └────────────────────┼──────────────────────┘
                    P2P Replication
                 (peer-to-peer sync)

         Phone Client
         (connects to any)
                 │
                 ▼
         ┌────────────────┐
         │ Desktop/Mobile │
         │ USSD Client    │
         └────────────────┘
```

---

## 🧪 TESTING SCENARIOS

### Test 1: Deposit on one server, check on another
```bash
# Terminal on Computer A (server_1):
python client/ussd_phone_client.py --phone 0754300000 --server http://192.168.1.10:8001

# Do: Deposit 10000
# Balance shows: 10000

# Terminal on Computer B (server_2):
python client/ussd_phone_client.py --phone 0754300000 --server http://192.168.1.11:8002

# Do: Check balance
# Should show: 10000 (replicated from server_1) ✅
```

### Test 2: Concurrent transactions
```bash
# Terminal 1 - Server A:
python client/ussd_phone_client.py --phone 0754300000 --server http://192.168.1.10:8001
# Do: Withdraw 3000

# Terminal 2 - Server B:
python client/ussd_phone_client.py --phone 0754300000 --server http://192.168.1.11:8002
# Do: Check balance
# Should show: 7000 (10000 - 3000) ✅
```

### Test 3: Offline server recovery
```bash
# Stop Server A:
# On Computer A, press Ctrl+C

# Make a transaction on Server B:
python client/ussd_phone_client.py --phone 0754300000 --server http://192.168.1.11:8002
# Do: Deposit 5000

# Restart Server A:
python main.py

# Check on Server A:
curl http://192.168.1.10:8001/health
# Should be healthy

# Check balance on Server A:
python client/ussd_phone_client.py --phone 0754300000 --server http://192.168.1.10:8001
# Should show: 12000 (7000 + 5000) ✅
```

---

## ⚠️ TROUBLESHOOTING

### Error: "Connection refused"
```bash
# Make sure server is running:
python main.py

# Verify port is open:
netstat -an | findstr 8001
```

### Error: "Cannot connect to database"
```bash
# Check PostgreSQL is running:
psql -h localhost -U postgres

# Create database if missing:
CREATE DATABASE mobile_money_system;

# Check DB_HOST in .env = localhost
```

### Error: "Cannot reach peer server"
```bash
# Verify peer URL is correct:
ping 192.168.1.11
curl http://192.168.1.11:8002/health

# Check PEER_SERVERS in .env file
# No spaces, comma-separated, other servers only
```

### Replication not working
```bash
# Check replication is enabled:
grep REPLICATION_ENABLED .env
# Should be: true

# Check logs for replication errors
tail -f logs/server.log | grep replication
```

### Port already in use
```bash
# Find process using port:
netstat -ano | findstr 8001

# Kill it (if safe):
taskkill /PID [PID] /F

# Or change SERVER_PORT in .env
```

---

## 📊 MONITORING & DEBUGGING

### View server logs:
```bash
# Watch for replication events:
tail -f logs/server.log | grep "replication\|sync"
```

### Check database replication status:
```bash
psql -h localhost -U postgres -d mobile_money_system

# View all accounts:
SELECT * FROM account;

# View transaction log:
SELECT * FROM transaction ORDER BY created_at DESC LIMIT 10;

# View replication log:
SELECT * FROM replication_log_entry ORDER BY created_at DESC LIMIT 10;
```

### Monitor peer heartbeats:
```bash
# Check if servers see each other
curl http://192.168.1.10:8001/peers
curl http://192.168.1.11:8002/peers
curl http://192.168.1.12:8003/peers

# Each should list healthy peers
```

---

## 🎯 NEXT STEPS

1. **Right now (30 mins):**
   - [ ] Note each computer's IP address
   - [ ] Install PostgreSQL & Redis on all 3 computers
   - [ ] Copy project to all 3 computers
   - [ ] Create .env file on each (copy template above)

2. **Start servers (5 mins):**
   - [ ] Run `python main.py` on Computer A
   - [ ] Run `python main.py` on Computer B
   - [ ] Run `python main.py` on Computer C
   - [ ] Verify all health checks pass

3. **Test system (15 mins):**
   - [ ] Run phone client on server A, deposit 10000
   - [ ] Run phone client on server B, check balance
   - [ ] Stop server A, test failover
   - [ ] Restart server A, verify sync

---

## KEY DIFFERENCES FROM CENTRAL DATABASE

| Aspect | Central DB | P2P (Current) |
|--------|--------|--------|
| Database location | One computer | Local on all 3 |
| Single point of failure | YES ⚠️ | NO ✅ |
| Network latency | Could be high | Low (local DB) |
| Replication | Automatic (single DB) | Peer-to-peer background job |
| Peer status | Master/slave | **All equal** |
| Failover | If central fails, all fail | Others continue working |
| Setup complexity | Easier | Slightly harder (PEER_SERVERS) |
| Scalability | Limited | Better (each peer scales) |

---

## 🚀 AUTOMATED SETUP (Optional)

```bash
python setup_multi_computer.py
```

Generates:
- .env files for each server
- Network diagram
- Personalized instructions

---

## 📞 DOCUMENTATION

- **P2P_DISTRIBUTED_DEPLOYMENT.md** - Full P2P deployment guide
- **DEPLOYMENT_REPORT.md** - Complete deployment report
- **PHONE_CLIENT_GUIDE.md** - Phone client usage
- **README.md** - System overview

---

**You've got this!** 🎉

All servers are equal. All are important. Any one can go down and the others keep working. That's the power of P2P! 💪
