"""
Multi-Computer Setup Wizard
Helps configure Mobile Money System across multiple machines
"""

import os
import sys
from pathlib import Path
from collections import OrderedDict

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║  MOBILE MONEY SYSTEM - MULTI-COMPUTER SETUP WIZARD          ║
║  Configure distributed deployment across your network       ║
╚══════════════════════════════════════════════════════════════╝
    """)

def get_input(prompt, default=None):
    """Get user input with optional default"""
    if default:
        prompt += f" [{default}]: "
    else:
        prompt += ": "
    
    value = input(prompt).strip()
    return value if value else default

def setup_database_computer():
    """Get info for central database computer"""
    print("\n" + "="*60)
    print("STEP 1: CENTRAL DATABASE COMPUTER")
    print("="*60)
    print("\nThis is where PostgreSQL & Redis run.")
    print("All servers will connect to this computer.")
    
    config = OrderedDict()
    config['db_computer_ip'] = get_input(
        "\nEnter IP address of database computer",
        "192.168.1.100"
    )
    config['db_password'] = get_input(
        "PostgreSQL password (choose secret)",
        "mobile_money_db"
    )
    config['db_name'] = get_input(
        "Database name",
        "mobile_money_system"
    )
    
    return config

def setup_server_computers():
    """Get info for app server computers"""
    print("\n" + "="*60)
    print("STEP 2: APP SERVER COMPUTERS")
    print("="*60)
    print("\nEnter details for each server computer.")
    print("Example: server_1 on Computer A at 192.168.1.10:8001\n")
    
    servers = []
    num_servers = int(get_input("How many servers? (2-10)", "3"))
    
    for i in range(1, num_servers + 1):
        print(f"\n--- Server {i} ---")
        server = OrderedDict()
        server['server_id'] = f"server_{i}"
        server['server_name'] = get_input(
            f"Server {i} name",
            f"Mobile Money Server {i}"
        )
        server['server_ip'] = get_input(
            f"Server {i} IP address",
            f"192.168.1.{10+i-1}"
        )
        server['server_port'] = 8000 + i
        servers.append(server)
    
    return servers

def setup_client_computer():
    """Get info for client computer (optional)"""
    print("\n" + "="*60)
    print("STEP 3: CLIENT COMPUTER (Optional)")
    print("="*60)
    print("\nPhone client can run from any computer.")
    print("Leave blank if running from same computer as a server.\n")
    
    client_ip = get_input(
        "Phone client computer IP (optional)",
        ""
    )
    
    return client_ip if client_ip else None

def generate_env_file(server_config, db_config, filename):
    """Generate .env file for a server"""
    
    return f"""# Mobile Money System - Server Configuration
# Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# ============= SERVER CONFIGURATION =============
SERVER_ID={server_config['server_id']}
SERVER_NAME={server_config['server_name']}
SERVER_HOST=0.0.0.0
SERVER_PORT={server_config['server_port']}

# ============= DATABASE CONFIGURATION =============
DATABASE_URL=postgresql://postgres:{db_config['db_password']}@{db_config['db_computer_ip']}:5432/{db_config['db_name']}
DB_HOST={db_config['db_computer_ip']}
DB_PORT=5432
DB_NAME={db_config['db_name']}
DB_USER=postgres
DB_PASSWORD={db_config['db_password']}

# ============= REDIS CONFIGURATION =============
REDIS_URL=redis://{db_config['db_computer_ip']}:6379/0
REDIS_HOST={db_config['db_computer_ip']}
REDIS_PORT=6379

# ============= APPLICATION CONFIGURATION =============
APP_ENV=production
APP_VERSION=1.0.0
APP_DEBUG=false
LOG_LEVEL=INFO
APP_NAME=Mobile Money System

# ============= SECURITY =============
SECRET_KEY=your-secret-key-change-in-production
API_KEY=default-api-key
API_SECRET=secret-key

# ============= NETWORK =============
PRIMARY_SERVER=http://{server_config['server_ip']}:{server_config['server_port']}
"""

def generate_setup_guide(servers, db_config):
    """Generate setup guide for all computers"""
    
    guide = """
╔══════════════════════════════════════════════════════════════╗
║            SETUP GUIDE FOR EACH COMPUTER                    ║
╚══════════════════════════════════════════════════════════════╝

STEP 1: SET UP CENTRAL DATABASE COMPUTER
─────────────────────────────────────────────────────────────

Computer: Central Database
IP: {db_ip}
Task: Install PostgreSQL & Redis

On Windows:
  1. Download PostgreSQL from https://www.postgresql.org/download/windows/
  2. Install with password: {db_password}
  3. Download Redis from https://github.com/microsoftarchive/redis/releases
  4. Extract and run redis-server.exe

OR use Docker:
  docker run -d --name postgres -e POSTGRES_PASSWORD={db_password} -p 5432:5432 postgres:15-alpine
  docker run -d --name redis -p 6379:6379 redis:7-alpine

Then create database:
  psql -U postgres
  CREATE DATABASE {db_name};
  \\q

Verify from another computer:
  psql -h {db_ip} -U postgres -d {db_name}


STEP 2: SET UP EACH APP SERVER COMPUTER
─────────────────────────────────────────────────────────────

For each server, create .env file with provided config and run:

  python main.py

Servers:
""".format(
        db_ip=db_config['db_computer_ip'],
        db_password=db_config['db_password'],
        db_name=db_config['db_name']
    )
    
    for server in servers:
        guide += f"""
  {server['server_id']} (Computer at {server['server_ip']}:{server['server_port']})
    - Copy .env-{server['server_id']} to project folder
    - Run: python main.py
    - Test: curl http://{server['server_ip']}:{server['server_port']}/health
"""
    
    guide += """

STEP 3: VERIFY ALL SERVERS RUNNING
─────────────────────────────────────────────────────────────

From any computer:
"""
    
    for server in servers:
        guide += f"  curl http://{server['server_ip']}:{server['server_port']}/health\n"
    
    guide += """

All should return: {"status": "healthy"}


STEP 4: RUN PHONE CLIENT
─────────────────────────────────────────────────────────────

From phone client computer:
  python client/ussd_phone_client.py --phone 075346363

Or connect to specific server:
  python client/ussd_phone_client.py --phone 075346363 --server http://{server_ip}:8001


STEP 5: TEST OPERATIONS
─────────────────────────────────────────────────────────────

In phone client:
  1. Select: 1 - Deposit Money
  2. Enter amount: 5000
  3. Select: 3 - Check Balance (shows 5000)
  4. Select: 2 - Withdraw Money
  5. Enter amount: 2000
  6. Select: 3 - Check Balance (shows 3000)


TROUBLESHOOTING
─────────────────────────────────────────────────────────────

"Connection refused" on port:
  - Ensure server is running: python main.py
  - Check .env file has correct database IP

"Cannot connect to database":
  - Verify PostgreSQL running on central computer
  - Test: psql -h {db_ip} -U postgres

"Cannot connect to Redis":
  - Verify Redis running on central computer
  - Test: redis-cli -h {db_ip} ping (should return PONG)

Servers not communicating:
  - Ensure all on same network
  - Test ping between computers
  - Check firewall allows ports 8001-8003


NETWORK TOPOLOGY
─────────────────────────────────────────────────────────────

""".format(db_ip=db_config['db_computer_ip'])
    
    guide += f"Database Computer: {db_config['db_computer_ip']}\n"
    
    for server in servers:
        guide += f"  ↓ connected from\n"
        guide += f"{server['server_id']}: {server['server_ip']}:{server['server_port']}\n"
    
    return guide

def save_configs(servers, db_config, output_dir="."):
    """Save .env files for each server"""
    output_path = Path(output_dir)
    
    # Create .env for each server
    for server in servers:
        env_file = output_path / f".env-{server['server_id']}"
        env_content = generate_env_file(server, db_config, str(env_file))
        
        with open(env_file, 'w') as f:
            f.write(env_content)
        
        print(f"✅ Created: {env_file}")
    
    # Create setup guide
    guide_file = output_path / "MULTI_COMPUTER_SETUP_GUIDE.txt"
    guide_content = generate_setup_guide(servers, db_config)
    
    with open(guide_file, 'w') as f:
        f.write(guide_content)
    
    print(f"✅ Created: {guide_file}")
    
    # Create network diagram
    diagram = create_network_diagram(servers, db_config)
    diagram_file = output_path / "NETWORK_DIAGRAM.txt"
    
    with open(diagram_file, 'w') as f:
        f.write(diagram)
    
    print(f"✅ Created: {diagram_file}")

def create_network_diagram(servers, db_config):
    """Create visual network diagram"""
    
    diagram = """
╔═══════════════════════════════════════════════════════════════╗
║          YOUR MULTI-COMPUTER NETWORK TOPOLOGY                ║
╚═══════════════════════════════════════════════════════════════╝

"""
    
    # Database computer
    diagram += f"""┌─────────────────────────┐
│  CENTRAL DATABASE       │
│  IP: {db_config['db_computer_ip']}         │
│  - PostgreSQL :5432     │
│  - Redis :6379          │
└────────────┬────────────┘
             │ (all servers connect here)
             │
"""
    
    # Server computers
    for i, server in enumerate(servers):
        if i < len(servers) - 1:
            diagram += f"      ┌────────┴────────┐\n"
        else:
            diagram += f"      ┌────────┴────────┐\n"
    
    diagram += "\n"
    
    for server in servers:
        diagram += f"""┌──────────────────────────┐
│ {server['server_id'].upper()}                  │
│ IP: {server['server_ip']}             │
│ PORT: {server['server_port']}                    │
│ {server['server_name']}     │
└──────────────────────────┘

"""
    
    diagram += """All servers connect to same PostgreSQL & Redis
Consistent hashing routes phones to nearest server
Auto-recovery if one server goes down
"""
    
    return diagram

def main():
    """Main wizard"""
    clear_screen()
    print_banner()
    
    print("This wizard will help you configure the mobile money system")
    print("to run across multiple computers on your local network.\n")
    
    input("Press Enter to continue...")
    
    # Gather information
    db_config = setup_database_computer()
    servers = setup_server_computers()
    client_ip = setup_client_computer()
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"\nDatabase Computer: {db_config['db_computer_ip']}")
    print(f"Database Password: {db_config['db_password']}")
    print(f"Database Name: {db_config['db_name']}")
    print(f"\nServer Computers: {len(servers)}")
    for server in servers:
        print(f"  - {server['server_id']}: {server['server_ip']}:{server['server_port']}")
    
    if client_ip:
        print(f"\nClient Computer: {client_ip}")
    
    save = input("\nSave configuration? (y/n): ").lower() == 'y'
    
    if save:
        save_configs(servers, db_config)
        print("\n✅ Configuration files saved!")
        print("\nNext steps:")
        print("1. Copy .env-server_* files to respective computers")
        print("2. Rename .env-server_1 to .env on server_1 computer")
        print("3. Start PostgreSQL & Redis on central computer")
        print("4. Run: python main.py on each server computer")
        print("5. Run: python client/ussd_phone_client.py on client computer")
        print("\nSee MULTI_COMPUTER_SETUP_GUIDE.txt for detailed instructions.")
    
    print("\n✨ Setup wizard complete!")

if __name__ == "__main__":
    main()
