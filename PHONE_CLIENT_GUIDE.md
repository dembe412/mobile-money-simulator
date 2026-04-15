# USSD Phone Client - User Guide

## Overview

The **USSD Phone Client** simulates a feature phone USSD interface that allows users to interact with the Mobile Money System using a text-based menu system, just like real feature phones.

## What is USSD?

**USSD (Unstructured Supplementary Service Data)** is:
- A technology used primarily on feature phones (not requiring internet)
- Works through dialing codes like `*165#` on any phone
- Displays menu-driven interfaces
- Used for mobile money systems like M-Pesa, MTN Mobile Money, etc.

Our implementation provides a Python-based USSD simulator that mimics this experience.

## Quick Start

### 1. Start the Server

First, generate and start your distributed servers:

```bash
# Generate docker-compose.yml with 3 servers
python generate_docker_compose.py --servers server_1:8001,server_2:8002,server_3:8003

# Start servers
docker-compose up
```

### 2. Run the Phone Client

In a new terminal:

```bash
# Run with default settings (localhost:8001)
python client/ussd_phone_client.py

# Run with specific phone number
python client/ussd_phone_client.py --phone 075346363

# Run with custom server
python client/ussd_phone_client.py --phone 075346363 --server http://localhost:8002
```

### 3. Use the Menu

Once started, you'll see:

```
┌─────────────────────────────────┐
│  MOBILE MONEY SERVICE           │
│  *165*                          │
├─────────────────────────────────┤
│ 1. Deposit Money                │
│ 2. Withdraw Money               │
│ 3. Check Balance                │
│ 4. Transaction History          │
│ 5. Settings                     │
│ 0. Exit                         │
└─────────────────────────────────┘
Enter choice (0-5):
```

## Usage Examples

### Create an Account (First Time)

When you first run the client with a new phone number, the system automatically creates an account:

```
🔍 Discovering nearest server...
Connected to server_1

📱 Welcome! Phone: 075346363
⏱️  Session started at 14:32:45
```

### Deposit Money

1. Press `1` from main menu
2. Enter amount: `5000`
3. Confirm: `yes`
4. See confirmation with new balance

### Withdraw Money

1. Press `2` from main menu
2. Enter amount: `2000`
3. Confirm: `yes`
4. See confirmation with new balance

### Check Balance

1. Press `3` from main menu
2. See your current balance instantly

### View Transaction History

1. Press `4` from main menu
2. See last 5 transactions showing:
   - Transaction type (deposit/withdraw)
   - Amount (+ for deposit, - for withdraw)
   - Date

### View Account Settings

1. Press `5` → `1` to see account info
2. Press `5` → `2` to see your phone number
3. Press `5` → `3` to see which server you're connected to
4. Press `5` → `4` to go back

### Exit

- Press `0` to exit
- Or press Ctrl+C to force exit

## How It Works

### Request Flow

```
User Input
    ↓
Phone Client (ussd_phone_client.py)
    ↓
MobileMoneyClient (mobile_money_client.py)
    ↓
Server Discovery (find nearest server)
    ↓
Remote Server (FastAPI endpoint)
    ↓
Database Operations
    ↓
Response → Phone Client → Display
```

### Session Management

- Each phone number gets a unique session
- Sessions auto-expire after 5 minutes of inactivity
- Session ID format: `{phone_number}_{timestamp}`
- User input buffer stored for multi-step operations

### Server Discovery

The client automatically discovers the nearest server using:
1. Consistent hashing algorithm
2. Hash ring with 150 virtual nodes per server
3. Request routing based on phone number

## Command Line Options

```bash
python client/ussd_phone_client.py [OPTIONS]

Options:
  --phone TEXT      Phone number (e.g., 075346363)
                    Default: Prompted for input
  
  --server TEXT     Server URL (e.g., http://localhost:8001)
                    Default: http://localhost:8001
  
  --help            Show this help message
```

## Examples

### Example 1: Basic Usage

```bash
$ python client/ussd_phone_client.py
Enter your phone number: 0712345678

🔍 Discovering nearest server...
Connected to server_1

📱 Welcome! Phone: 0712345678
⏱️  Session started at 14:30:22

Main Menu:
1. Deposit Money

Enter choice (0-5): 1

💰 DEPOSIT MONEY
Enter amount to deposit: 10000
Confirm: yes

Processing...

┌─────────────────────────────────┐
│  SUCCESS                        │
│  Deposit completed!             │
├─────────────────────────────────┤
│ Amount: 10000.0
│ Balance: 10000.0
│ Time: 14:30:45
└─────────────────────────────────┘
```

### Example 2: Multiple Operations

```bash
$ python client/ussd_phone_client.py --phone 0723456789 --server http://localhost:8002

# First deposit
Enter choice: 1
Amount: 5000
Result: ✓ Success, Balance: 5000

# Check balance
Enter choice: 3
Result: Balance: 5000

# Withdraw some
Enter choice: 2
Amount: 1500
Result: ✓ Success, Balance: 3500

# Check transactions
Enter choice: 4
Recent Transactions:
1. withdraw - 1500.0 on 2024-04-08
2. deposit  + 5000.0 on 2024-04-08
```

## Understanding the Response Format

All operations return structured responses:

```python
{
    "success": bool,        # Operation successful?
    "message": str,         # Human-readable message
    "data": {              # Operation-specific data
        # varies by operation
    }
}
```

### Deposit Response Example
```python
{
    "success": True,
    "message": "Deposit successful",
    "data": {
        "amount": 5000,
        "balance": 5000,
        "timestamp": "2024-04-08T14:30:45"
    }
}
```

### Balance Response Example
```python
{
    "success": True,
    "message": "Balance retrieved",
    "data": {
        "account_id": "075346363",
        "balance": 5000,
        "account_holder": "User"
    }
}
```

## Troubleshooting

### "Server discovery failed"
- Ensure servers are running: `docker-compose ps`
- Check server URL: `--server http://localhost:8001`
- Verify network connectivity

### "Connection refused"
- Servers not running
- Wrong server port
- Use `docker-compose up` to start servers

### "Session has expired"
- Session times out after 5 minutes of inactivity
- Simply restart the client: `python client/ussd_phone_client.py`

### "Invalid choice"
- Menu only accepts 0-5
- Ensure you're entering a single digit
- No spaces before/after your choice

## Session Features

- **Timeout**: 5 minutes of inactivity
- **Persistence**: Session persists across multiple menu operations
- **Auto-creation**: Account auto-created on first use
- **Multi-step save**: Input buffer stores data between menu screens

## Integration Points

### Using in Python Code

```python
from client.mobile_money_client import MobileMoneyClient

client = MobileMoneyClient(base_url="http://localhost:8001")

# Deposit
result = client.deposit(
    account_id="075346363",
    phone_number="075346363",
    amount=5000
)

if result['success']:
    print(f"Balance: {result['data']['balance']}")
else:
    print(f"Error: {result['message']}")
```

### Phone Client as a Library

```python
from client.ussd_phone_client import USSDPhoneClient

client = USSDPhoneClient(
    phone_number="075346363",
    server_url="http://localhost:8001"
)
client.run()
```

## API Endpoints Used by Phone Client

The phone client interacts with these server endpoints:

```
GET  /api/v1/routing/discover/{phone_number}    - Find nearest server
POST /api/v1/account/create                     - Create account
GET  /api/v1/account/{account_id}               - Get account info
POST /api/v1/operation/deposit                  - Deposit funds
POST /api/v1/operation/withdraw                 - Withdraw funds
POST /api/v1/operation/balance                  - Check balance
POST /api/v1/operation/transactions             - Get history
POST /api/v1/ussd                               - USSD request (optional)
```

## Real-World USSD Code Format

While our phone client is menu-driven, the system supports real USSD codes:

```
*165*1*075346363*5000#    - Deposit 5000 to yourself
*165*2*075346363*2000#    - Withdraw 2000 from yourself
*165*3*075346363*#        - Check balance
*165*4*075346363*5#       - Get last 5 transactions
```

You can also send these directly via `client.ussd_request()`:

```python
result = client.ussd_request("*165*1*075346363*5000#", "075346363")
```

## Performance Metrics

On a single workstation with 3 servers:

| Operation | Avg Time | Notes |
|-----------|----------|-------|
| Deposit   | 50-100ms | Includes locking & replication |
| Withdraw  | 50-100ms | Includes balance check |
| Balance   | 20-30ms  | Read-only, no lock needed |
| History   | 30-50ms  | Depends on number of transactions |

## Next Steps

1. **Multiple Users**: Run multiple phone clients simultaneously
2. **Stress Testing**: Use `test_client.py` for batch operations
3. **Real SMS Gateway**: Integrate with SMS provider (Twilio, Africa's Talking)
4. **Web Dashboard**: Build web interface for account management
5. **P2P Transfers**: Add peer-to-peer money transfer feature

## Support & Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### View Server Logs

```bash
docker-compose logs -f server_1
```

### Network Test

```bash
curl http://localhost:8001/health
```

## Summary

The USSD Phone Client provides:
- ✓ Feature phone-like experience
- ✓ Menu-driven interface
- ✓ Automatic server discovery
- ✓ Session management
- ✓ Error handling
- ✓ Transaction history
- ✓ Real-time balance
- ✓ Multi-server support

Start using: `python client/ussd_phone_client.py`
