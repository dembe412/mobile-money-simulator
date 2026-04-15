# Easy Server Setup - Just Add Server ID & Port

Instead of manually editing `docker-compose.yml`, just use the generator script!

## 🚀 Quick Usage

### Default (3 servers: 8001, 8002, 8003)
```bash
python generate_docker_compose.py
docker-compose up
```

## ➕ Add More Servers

### 5 Servers (8001-8005)
```bash
python generate_docker_compose.py --servers \
  server_1:8001,server_2:8002,server_3:8003,server_4:8004,server_5:8005

docker-compose up
```

### 10 Servers (9001-9010)
```bash
python generate_docker_compose.py --servers \
  server_1:9001,server_2:9002,server_3:9003,server_4:9004,server_5:9005,\
  server_6:9006,server_7:9007,server_8:9008,server_9:9009,server_10:9010

docker-compose up
```

### Custom Names
```bash
python generate_docker_compose.py --servers \
  primary:8001,secondary:8002,tertiary:8003,replica_1:8004,replica_2:8005

docker-compose up
```

## 📝 Examples

### 3 Servers (Default)
```bash
python generate_docker_compose.py
```
Creates:
- server_1:8001
- server_2:8002
- server_3:8003

### 2 Servers (Light Setup)
```bash
python generate_docker_compose.py --servers server_1:8001,server_2:8002
```
Creates:
- server_1:8001
- server_2:8002

### 7 Servers (Large Setup)
```bash
python generate_docker_compose.py --servers \
  server_1:8001,server_2:8002,server_3:8003,server_4:8004,\
  server_5:8005,replica_1:8006,replica_2:8007
```
Creates:
- server_1:8001
- server_2:8002
- server_3:8003
- server_4:8004
- server_5:8005
- replica_1:8006
- replica_2:8007

## 🔧 Options

```bash
python generate_docker_compose.py --help
```

### Available Options
- `--servers`: Comma-separated list of "id:port" pairs
- `--output`: Output file (default: docker-compose.yml)

## 📋 What Gets Generated

The script auto-creates:
- **PostgreSQL** (single shared database)
- **Redis** (message queue)
- **N Servers** (exactly as you specify)

All servers:
- Use the same PostgreSQL database
- Use the same Redis instance
- Auto-configure environment variables
- Have their own port
- Can be added/removed on demand

## 🎯 Workflow

```bash
# 1. Add more servers
python generate_docker_compose.py --servers \
  server_1:8001,server_2:8002,server_3:8003,server_4:8004

# 2. Start system
docker-compose up

# 3. Test
python test_client.py

# 4. Stop
docker-compose down

# 5. Change setup? Just regenerate!
python generate_docker_compose.py --servers server_1:8001,server_2:8002
docker-compose up
```

## ✅ That's It!

No more manual editing of `docker-compose.yml`. Just specify servers and ports!

```bash
# Simple!
python generate_docker_compose.py --servers server_1:8001,server_2:8002,server_3:8003
docker-compose up
```
