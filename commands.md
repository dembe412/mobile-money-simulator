# Git Bash Commands for Distributed Run

Use these commands from the repository root in Git Bash.

## Server PC 1 - 10.176.230.225

```bash
source .venv/Scripts/activate

export SERVER_ID=server_1
export SERVER_NAME="Server 1"
export SERVER_HOST=10.176.230.225
export SERVER_PORT=8001
python main.py
```

## Server PC 2 - 10.176.230.123

```bash
source .venv/Scripts/activate

export SERVER_ID=server_2
export SERVER_NAME="Server 2"
export SERVER_HOST=10.176.230.123
export SERVER_PORT=8001
python main.py
```

## Server PC 3 - 10.176.230.191

```bash
source .venv/Scripts/activate

export SERVER_ID=server_3
export SERVER_NAME="Server 3"
export SERVER_HOST=10.176.230.191
export SERVER_PORT=8001
python main.py
```

## Client PC

```bash
source .venv/Scripts/activate

python client/ussd_phone_client.py --servers http://10.176.230.225:8001,http://10.176.230.123:8001,http://10.176.230.191:8001
```

## Client With Phone Number

```bash
python client/ussd_phone_client.py --phone 0700000001 --servers http://10.176.230.225:8001,http://10.176.230.123:8001,http://10.176.230.191:8001
```

## Windows Firewall Rule

Run this on each server PC if other machines cannot reach the node:

```powershell
powershell -Command "New-NetFirewallRule -DisplayName 'MobileMoney 8001' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8001"
```
