"""
Generate docker-compose.yml dynamically
Just specify servers and ports, everything else is auto-generated
"""
import yaml
import sys
from pathlib import Path


def generate_docker_compose(servers_config):
    """
    Generate docker-compose.yml from server configuration
    
    Args:
        servers_config: List of dicts with 'id' and 'port' keys
        Example: [
            {'id': 'server_1', 'port': 8001},
            {'id': 'server_2', 'port': 8002},
            {'id': 'server_3', 'port': 8003},
        ]
    """
    
    compose = {
        'version': '3.8',
        'services': {
            'postgres': {
                'image': 'postgres:15-alpine',
                'container_name': 'mobile_money_db',
                'environment': {
                    'POSTGRES_DB': 'mobile_money_system',
                    'POSTGRES_USER': 'postgres',
                    'POSTGRES_PASSWORD': 'postgres'
                },
                'ports': ['5432:5432'],
                'volumes': ['postgres_data:/var/lib/postgresql/data'],
                'networks': ['mobile_money_network'],
                'healthcheck': {
                    'test': ['CMD-SHELL', 'pg_isready -U postgres'],
                    'interval': '10s',
                    'timeout': '5s',
                    'retries': 5
                }
            },
            'redis': {
                'image': 'redis:7-alpine',
                'container_name': 'mobile_money_redis',
                'ports': ['6379:6379'],
                'volumes': ['redis_data:/data'],
                'networks': ['mobile_money_network'],
                'healthcheck': {
                    'test': ['CMD', 'redis-cli', 'ping'],
                    'interval': '10s',
                    'timeout': '5s',
                    'retries': 5
                }
            }
        },
        'volumes': {
            'postgres_data': {},
            'redis_data': {}
        },
        'networks': {
            'mobile_money_network': {
                'driver': 'bridge'
            }
        }
    }
    
    # Add servers dynamically
    for server in servers_config:
        server_id = server['id']
        port = server['port']
        
        service_name = server_id.lower()
        
        compose['services'][service_name] = {
            'build': {
                'context': '.',
                'dockerfile': 'docker/Dockerfile'
            },
            'container_name': f'mobile_money_{service_name}',
            'environment': {
                'SERVER_ID': server_id,
                'SERVER_NAME': f'{server_id.replace("_", " ").title()}',
                'SERVER_HOST': '0.0.0.0',
                'SERVER_PORT': str(port),
                'DB_HOST': 'postgres',
                'DB_PORT': '5432',
                'DB_USER': 'postgres',
                'DB_PASSWORD': 'postgres',
                'DB_NAME': 'mobile_money_system',
                'REDIS_HOST': 'redis',
                'REDIS_PORT': '6379',
                'APP_ENV': 'development',
                'APP_DEBUG': 'true'
            },
            'ports': [f'{port}:{port}'],
            'depends_on': {
                'postgres': {'condition': 'service_healthy'},
                'redis': {'condition': 'service_healthy'}
            },
            'networks': ['mobile_money_network'],
            'volumes': [
                './:/app',
                './logs:/app/logs'
            ],
            'command': 'python main.py'
        }
    
    return compose


def save_docker_compose(compose_dict, output_file='docker-compose.yml'):
    """Save docker-compose dict to YAML file"""
    with open(output_file, 'w') as f:
        yaml.dump(compose_dict, f, default_flow_style=False, sort_keys=False)
    print(f"✓ Generated {output_file}")


def print_usage():
    """Print usage instructions"""
    print("\n" + "="*70)
    print("  DOCKER-COMPOSE GENERATOR FOR MOBILE MONEY SYSTEM")
    print("="*70 + "\n")
    
    print("Usage: python generate_docker_compose.py --servers SERVER_CONFIG\n")
    
    print("Examples:\n")
    
    print("1. Default (3 servers on ports 8001-8003):")
    print("   python generate_docker_compose.py\n")
    
    print("2. Custom servers (specify as 'id:port,id:port,...'):")
    print("   python generate_docker_compose.py --servers server_1:8001,server_2:8002,server_3:8003\n")
    
    print("3. Many servers:")
    print("   python generate_docker_compose.py --servers server_1:8001,server_2:8002,server_3:8003,server_4:8004,server_5:8005\n")
    
    print("4. Custom names:")
    print("   python generate_docker_compose.py --servers primary:8001,secondary:8002,tertiary:8003\n")
    
    print("Then start with:")
    print("   docker-compose up\n")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Generate docker-compose.yml for Mobile Money System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_docker_compose.py
  python generate_docker_compose.py --servers server_1:8001,server_2:8002,server_3:8003
  python generate_docker_compose.py --servers server_1:9001,server_2:9002,replica_1:9003,replica_2:9004
        """
    )
    
    parser.add_argument(
        '--servers',
        type=str,
        default='server_1:8001,server_2:8002,server_3:8003',
        help='Comma-separated servers (id:port). Default: server_1:8001,server_2:8002,server_3:8003'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='docker-compose.yml',
        help='Output file path. Default: docker-compose.yml'
    )
    
    args = parser.parse_args()
    
    # Parse servers
    servers = []
    try:
        for server_spec in args.servers.split(','):
            parts = server_spec.strip().split(':')
            if len(parts) != 2:
                raise ValueError(f"Invalid format: {server_spec}. Use 'id:port'")
            
            server_id, port = parts
            server_id = server_id.strip()
            port = int(port.strip())
            
            servers.append({'id': server_id, 'port': port})
    
    except (ValueError, IndexError) as e:
        print(f"❌ Error parsing servers: {e}")
        print_usage()
        sys.exit(1)
    
    # Validate
    if not servers:
        print("❌ No servers specified")
        print_usage()
        sys.exit(1)
    
    # Check for duplicate ports
    ports = [s['port'] for s in servers]
    if len(ports) != len(set(ports)):
        print("❌ Duplicate ports detected")
        sys.exit(1)
    
    # Check for duplicate IDs
    ids = [s['id'] for s in servers]
    if len(ids) != len(set(ids)):
        print("❌ Duplicate server IDs detected")
        sys.exit(1)
    
    # Generate
    print("\n📝 Generating docker-compose.yml...\n")
    print(f"Servers to create:")
    for server in servers:
        print(f"  ✓ {server['id']:20s} → port {server['port']}")
    print()
    
    compose = generate_docker_compose(servers)
    save_docker_compose(compose, args.output)
    
    print("\n✅ Success! Now run:")
    print(f"   docker-compose up\n")


if __name__ == '__main__':
    main()
