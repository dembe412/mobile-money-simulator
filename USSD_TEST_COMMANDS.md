# USSD Test Commands

Open 4 Git Bash terminals in `d:/mobile-money-simulator`.

## Terminal 1: Server 1

```bash
cd /d/mobile-money-simulator && SERVER_ID=server_1 SERVER_NAME="Node 1" SERVER_PORT=8001 python main.py
```

## Terminal 2: Server 2

```bash
cd /d/mobile-money-simulator && SERVER_ID=server_2 SERVER_NAME="Node 2" SERVER_PORT=8002 python main.py
```

## Terminal 3: Server 3

```bash
cd /d/mobile-money-simulator && SERVER_ID=server_3 SERVER_NAME="Node 3" SERVER_PORT=8003 python main.py
```

## Terminal 4: USSD and API Tests

Wait 5 seconds after starting the servers, then run these one-line commands.

### Create accounts

```bash
cd /d/mobile-money-simulator && curl -X POST http://127.0.0.1:8001/api/v1/account/create -H "Content-Type: application/json" -d '{"phone_number":"0700000001","account_holder_name":"Alice Mwangi","initial_balance":50000}' && curl -X POST http://127.0.0.1:8002/api/v1/account/create -H "Content-Type: application/json" -d '{"phone_number":"0700000002","account_holder_name":"Bob Kamau","initial_balance":50000}' && curl -X POST http://127.0.0.1:8003/api/v1/account/create -H "Content-Type: application/json" -d '{"phone_number":"0700000003","account_holder_name":"Carol Wanjiru","initial_balance":50000}'
```

### USSD create account

```bash
cd /d/mobile-money-simulator && curl -X POST http://127.0.0.1:8001/api/v1/ussd -H "Content-Type: application/json" -d '{"ussd_input":"*165*1*0700000099*10000#"}'
```

### USSD check balance

```bash
cd /d/mobile-money-simulator && curl -X POST http://127.0.0.1:8001/api/v1/ussd -H "Content-Type: application/json" -d '{"ussd_input":"*165*3*0700000001#"}'
```

### USSD withdraw

```bash
cd /d/mobile-money-simulator && curl -X POST http://127.0.0.1:8002/api/v1/ussd -H "Content-Type: application/json" -d '{"ussd_input":"*165*2*0700000002*500#"}'
```

### Regular API withdraw

```bash
cd /d/mobile-money-simulator && curl -X POST http://127.0.0.1:8001/api/v1/operation/withdraw -H "Content-Type: application/json" -d '{"phone_number":"0700000001","amount":1000,"client_reference":"my-ref-001"}'
```

### Regular API deposit

```bash
cd /d/mobile-money-simulator && curl -X POST http://127.0.0.1:8002/api/v1/operation/deposit -H "Content-Type: application/json" -d '{"phone_number":"0700000002","amount":500,"client_reference":"dep-ref-001"}'
```

### Regular API check balance

```bash
cd /d/mobile-money-simulator && curl -X POST http://127.0.0.1:8001/api/v1/operation/balance -H "Content-Type: application/json" -d '{"phone_number":"0700000001"}'
```

### Regular API transfer

```bash
cd /d/mobile-money-simulator && curl -X POST http://127.0.0.1:8001/api/v1/operation/transfer -H "Content-Type: application/json" -d '{"from_account_id":1,"from_phone_number":"0700000001","to_phone_number":"0700000002","amount":2000,"client_reference":"txfr-001"}'
```

### Check cluster status

```bash
cd /d/mobile-money-simulator && curl http://127.0.0.1:8001/api/v1/cluster/status | python -m json.tool
```

### Interactive USSD client

```bash
cd /d/mobile-money-simulator && python scripts/ussd_phone_client.py
```

## Kill-and-restart test

While the servers are running, stop server_1 with Ctrl+C in Terminal 1, then run this from Terminal 4:

```bash
cd /d/mobile-money-simulator && curl -X POST http://127.0.0.1:8002/api/v1/operation/withdraw -H "Content-Type: application/json" -d '{"phone_number":"0700000002","amount":100,"client_reference":"test-001"}'
```

Restart server_1 with:

```bash
cd /d/mobile-money-simulator && SERVER_ID=server_1 SERVER_NAME="Node 1" SERVER_PORT=8001 python main.py
```

## Multi-machine version

Use this when the servers run on different PCs. Replace `MACHINE_1_IP`, `MACHINE_2_IP`, and `MACHINE_3_IP` with the real LAN IPs.

```bash
cd /d/mobile-money-simulator && SERVER_ID=server_1 SERVER_NAME="Node 1" SERVER_HOST=0.0.0.0 SERVER_PORT=8001 python main.py
```

```bash
cd /d/mobile-money-simulator && SERVER_ID=server_2 SERVER_NAME="Node 2" SERVER_HOST=0.0.0.0 SERVER_PORT=8002 python main.py
```

```bash
cd /d/mobile-money-simulator && SERVER_ID=server_3 SERVER_NAME="Node 3" SERVER_HOST=0.0.0.0 SERVER_PORT=8003 python main.py
```

```bash
curl -X POST http://MACHINE_1_IP:8001/api/v1/ussd -H "Content-Type: application/json" -d '{"ussd_input":"*165*3*0700000001#"}'
```

```bash
curl -X POST http://MACHINE_2_IP:8002/api/v1/operation/withdraw -H "Content-Type: application/json" -d '{"phone_number":"0700000002","amount":500,"client_reference":"remote-001"}'
```

```bash
curl -X POST http://MACHINE_3_IP:8003/api/v1/operation/balance -H "Content-Type: application/json" -d '{"phone_number":"0700000003"}'
```

