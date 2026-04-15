# Quick Start Guide - Mobile Money System

## 🚀 Start in 5 Minutes

### Option 1: Docker Compose (Recommended)

```bash
# 1. Generate server configuration
python generate_docker_compose.py --servers server_1:8001,server_2:8002,server_3:8003

# 2. Start all services
docker-compose up -d

# 3. Wait for services to start
docker-compose ps

# 4. Run phone client (feature phone interface)
python client/ussd_phone_client.py

# 5. Or run test client (integration tests)
python test_client.py

# 6. Access API directly
# Server 1: http://localhost:8001
# Server 2: http://localhost:8002
# Server 3: http://localhost:8003
```

### Option 2: Manual Setup (Linux/Mac)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create PostgreSQL database
createdb mobile_money_system

# 3. Start Redis
redis-server &

# 4. Terminal 1 - Server 1
export SERVER_ID=server_1 SERVER_PORT=8001
python main.py

# 5. Terminal 2 - Server 2
export SERVER_ID=server_2 SERVER_PORT=8002
python main.py

# 6. Terminal 3 - Server 3
export SERVER_ID=server_3 SERVER_PORT=8003
python main.py

# 7. Terminal 4 - Run tests
python test_client.py
```

### Option 2b: Manual Setup (Windows PowerShell)

```powershell
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create PostgreSQL database
createdb mobile_money_system

# 3. Start Redis
redis-server

# 4. PowerShell 1 - Server 1
$env:SERVER_ID="server_1"; $env:SERVER_PORT="8001"; python main.py

# 5. PowerShell 2 - Server 2
$env:SERVER_ID="server_2"; $env:SERVER_PORT="8002"; python main.py

# 6. PowerShell 3 - Server 3
$env:SERVER_ID="server_3"; $env:SERVER_PORT="8003"; python main.py

# 7. PowerShell 4 - Run tests
python test_client.py
```

---

## 📝 Quick Examples

### Python Client Usage

```python
from client.mobile_money_client import MobileMoneyClient

client = MobileMoneyClient()

# Create account
success, response = client.create_account("075346363", "John Doe", 10000)

# Withdraw
success, response = client.withdraw(account_id=1, phone_number="075346363", amount=1000)

# Check balance
success, response = client.check_balance(account_id=1)

# Deposit
success, response = client.deposit(account_id=1, phone_number="075346363", amount=500)

# USSD
success, response = client.ussd_request("*165*2*075346363*1000#")

# Discover server
success, url, routing = client.discover_server("075346363")
```

### cURL Commands

```bash
# Create Account
curl -X POST http://localhost:8001/api/v1/account/create \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"075346363","account_holder_name":"John","initial_balance":10000}'

# Withdraw
curl -X POST http://localhost:8001/api/v1/operation/withdraw \
  -H "Content-Type: application/json" \
  -d '{"account_id":1,"phone_number":"075346363","amount":1000}'

# Check Balance
curl -X POST http://localhost:8001/api/v1/operation/balance \
  -H "Content-Type: application/json" \
  -d '{"account_id":1}'

# USSD
curl -X POST http://localhost:8001/api/v1/ussd \
  -H "Content-Type: application/json" \
  -d '{"ussd_input":"*165*2*075346363*1000#"}'

# Health Check
curl http://localhost:8001/health

# Server Status
curl http://localhost:8001/status

# Hash Ring Status
curl http://localhost:8001/api/v1/hash-ring/status

# Discover Server
curl http://localhost:8001/api/v1/routing/discover/075346363
```

---

## 🔍 Monitoring

### Logs
```bash
tail -f logs/server.log

# Filter by server
grep "server_1" logs/server.log

# Filter by operation
grep "withdraw\|deposit" logs/server.log
```

### Health Checks
```bash
# Check all servers
for port in 8001 8002 8003; do
  echo "Server $port:"
  curl http://localhost:$port/health
  echo ""
done
```

### Database
```bash
# Connect to database
psql -U postgres -d mobile_money_system

# List accounts
SELECT account_id, phone_number, account_holder_name, balance FROM accounts;

# List recent transactions
SELECT * FROM transactions ORDER BY created_at DESC LIMIT 10;

# Check locks
SELECT * FROM account_locks WHERE expires_at > NOW();

# Server status
SELECT * FROM server_status;
```

---

## 🚨 Troubleshooting

### Port Already in Use
```bash
# Find process using port
lsof -i :8001

# Kill process
kill -9 <PID>

# Windows: Find and kill
netstat -ano | findstr :8001
taskkill /PID <PID> /F
```

### Database Connection Failed
```bash
# Check PostgreSQL is running
psql -h localhost -U postgres -d mobile_money_system -c "SELECT 1"

# Reset database
dropdb mobile_money_system
createdb mobile_money_system

# Docker: Reset database
docker-compose down -v
docker-compose up
```

### Redis Connection Failed
```bash
# Check Redis is running
redis-cli ping

# If not running:
redis-server  # Linux/Mac
redis-server.exe  # Windows
```

### Application Won't Start
```bash
# Check environment variables
echo $SERVER_ID
echo $SERVER_PORT

# Check logs
cat logs/server.log

# Run in debug mode
export LOG_LEVEL=DEBUG
export APP_DEBUG=true
python main.py
```

---

## 📊 Testing Scenarios

### Scenario 1: Basic Withdraw
```
1. Create account: 075346363, Balance: 10000
2. Withdraw: 1000 KES
Expected: Balance = 9000
```

### Scenario 2: Idempotency
```
1. Create account: 0721234567, Balance: 5000
2. Submit withdraw 500 three times with same request ID
Expected: Balance = 4500 (deducted only once)
```

### Scenario 3: Server Failover
```
1. Create account: 0728765432, Balance: 8000
2. Withdraw 1000 from Server 1
3. Kill Server 1
4. Check balance from Server 2 (should be 7000)
5. Withdraw 500 from Server 3
Expected: Final balance = 6500
```

### Scenario 4: Concurrent Operations
```
1. Create account, Balance: 10000
2. Simultaneously:
   - Withdraw 1000 (locked)
   - Withdraw 2000 (wait for lock)
   - Check balance (reads current)
Expected: Balance = 7000, both withdraws succeed
```

---

## 📚 API Documentation

Full interactive docs available at:
```
http://localhost:8001/docs
http://localhost:8002/docs
http://localhost:8003/docs
```

---

## 🔐 Security Notes

- Change `REQUEST_SIGNING_KEY` in production
- Use HTTPS for external clients
- Implement rate limiting
- Add authentication/authorization
- Monitor for suspicious patterns

---

## 📈 Scaling

### Add More Servers
Edit `docker-compose.yml`:
```yaml
server_4:
  # Copy server_3 config
  # Change port to 8004
  environment:
    SERVER_ID: server_4
    SERVER_PORT: 8004
```

### Scale Horizontally
```bash
docker-compose up -d --scale app=5
```

---

## 🎓 Learning Resources

- **USSD Format**: `*165*operation*phone*amount`
  - Operations: 1=Deposit, 2=Withdraw, 3=Balance, 4=Mini Statement
  
- **Consistent Hashing**: Routes same phone to same server
  - Reduces cache misses
  - Enables better load distribution
  
- **Pessimistic Locking**: Prevents race conditions
  - Account locked during operation
  - Automatic unlock after timeout
  
- **Request Idempotency**: Safely retry failed requests
  - Unique request IDs prevent duplicates
  - Cached responses for retries

---

## 📞 Support

For issues:
1. Check logs: `tail -f logs/server.log`
2. Verify servers running: `curl http://localhost:8001/health`
3. Check database: `psql -U postgres -d mobile_money_system`
4. Enable debug: `export LOG_LEVEL=DEBUG`

---

**Ready to start? Run: `docker-compose up` 🚀**
