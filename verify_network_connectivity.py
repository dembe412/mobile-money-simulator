"""
Multi-Computer Network Verification
Tests connectivity between all servers in distributed setup
"""

import socket
import requests
import sys
from pathlib import Path
from datetime import datetime

def test_host_reachable(ip, port=None):
    """Test if computer/service is reachable"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        
        if port:
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        else:
            sock.close()
            return True
    except:
        return False

def test_http_service(url):
    """Test if HTTP service responds"""
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except:
        return False

def get_server_info(url):
    """Get server status and info"""
    try:
        response = requests.get(f"{url}/status", timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def test_database_connection(host, port, user, password, database):
    """Test PostgreSQL connection"""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=5
        )
        conn.close()
        return True
    except ImportError:
        return None  # psycopg2 not installed
    except:
        return False

def test_redis_connection(host, port):
    """Test Redis connection"""
    try:
        import redis
        r = redis.Redis(host=host, port=port, socket_connect_timeout=5)
        r.ping()
        return True
    except ImportError:
        return None  # redis not installed
    except:
        return False

def main():
    """Interactive network verification"""
    
    print("\n" + "="*70)
    print("MOBILE MONEY SYSTEM - MULTI-COMPUTER NETWORK VERIFICATION")
    print("="*70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Get configuration
    print("Enter your network configuration:")
    db_ip = input("Database Computer IP (e.g., 192.168.1.100): ").strip()
    db_password = input("Database Password: ").strip()
    
    servers = []
    while True:
        server_id = input("Server ID (e.g., server_1) or 'done': ").strip()
        if server_id.lower() == 'done':
            break
        
        server_ip = input(f"  IP address for {server_id}: ").strip()
        server_port = input(f"  Port number (default 8001): ").strip()
        
        servers.append({
            'id': server_id,
            'ip': server_ip,
            'port': int(server_port) if server_port else 8001
        })
    
    print("\n" + "="*70)
    print("VERIFICATION TESTS")
    print("="*70)
    
    results = {
        'passed': 0,
        'failed': 0,
        'issues': []
    }
    
    # Test database connectivity
    print(f"\n[1] DATABASE CONNECTIVITY")
    print(f"    Testing: {db_ip}:5432")
    
    db_reachable = test_host_reachable(db_ip, 5432)
    if db_reachable:
        print(f"    ✅ Network reachable (port 5432)")
        results['passed'] += 1
    else:
        print(f"    ⚠️  Cannot reach port 5432")
        results['failed'] += 1
        results['issues'].append(f"Database port not reachable at {db_ip}:5432")
    
    db_conn = test_database_connection(db_ip, 5432, 'postgres', db_password, 'mobile_money_system')
    if db_conn is True:
        print(f"    ✅ PostgreSQL connected successfully")
        results['passed'] += 1
    elif db_conn is None:
        print(f"    ⚠️  psycopg2 not installed (cannot verify DB connection)")
        results['issues'].append("Install psycopg2: pip install psycopg2-binary")
    else:
        print(f"    ❌ PostgreSQL authentication failed")
        results['failed'] += 1
        results['issues'].append(f"Database connection failed - check password")
    
    # Test Redis connectivity
    print(f"\n[2] REDIS CONNECTIVITY")
    print(f"    Testing: {db_ip}:6379")
    
    redis_reachable = test_host_reachable(db_ip, 6379)
    if redis_reachable:
        print(f"    ✅ Network reachable (port 6379)")
        results['passed'] += 1
    else:
        print(f"    ⚠️  Cannot reach port 6379")
        results['failed'] += 1
        results['issues'].append(f"Redis port not reachable at {db_ip}:6379")
    
    redis_conn = test_redis_connection(db_ip, 6379)
    if redis_conn is True:
        print(f"    ✅ Redis connected successfully")
        results['passed'] += 1
    elif redis_conn is None:
        print(f"    ⚠️  redis-py not installed (cannot verify Redis connection)")
        results['issues'].append("Install redis: pip install redis")
    else:
        print(f"    ❌ Redis connection failed")
        results['failed'] += 1
        results['issues'].append(f"Redis connection failed - check if running")
    
    # Test each server
    print(f"\n[3] APP SERVER CONNECTIVITY ({len(servers)} servers)")
    
    for i, server in enumerate(servers, 1):
        print(f"\n    Server {i}: {server['id']} ({server['ip']}:{server['port']})")
        
        server_url = f"http://{server['ip']}:{server['port']}"
        health_url = f"{server_url}/health"
        
        # Network reachability
        reachable = test_host_reachable(server['ip'], server['port'])
        if reachable:
            print(f"      ✅ Network reachable")
            results['passed'] += 1
        else:
            print(f"      ❌ Cannot reach {server['ip']}:{server['port']}")
            results['failed'] += 1
            results['issues'].append(f"{server['id']} not reachable")
            continue
        
        # HTTP service
        http_ok = test_http_service(health_url)
        if http_ok:
            print(f"      ✅ HTTP service responding")
            results['passed'] += 1
        else:
            print(f"      ⚠️  HTTP not responding at {health_url}")
            results['failed'] += 1
            results['issues'].append(f"{server['id']} HTTP not responding")
            continue
        
        # Server status
        info = get_server_info(server_url)
        if info:
            status = info.get('status', 'unknown')
            server_id = info.get('server_id', 'unknown')
            print(f"      ✅ Server status: {status}")
            print(f"      ℹ️  Server ID: {server_id}")
            results['passed'] += 1
        else:
            print(f"      ⚠️  Could not retrieve server info")
    
    # Test server-to-server connectivity
    if len(servers) > 1:
        print(f"\n[4] SERVER-TO-SERVER CONNECTIVITY")
        
        for i, server1 in enumerate(servers):
            for server2 in servers[i+1:]:
                print(f"    {server1['id']} → {server2['id']}")
                
                reachable = test_host_reachable(server2['ip'], server2['port'])
                if reachable:
                    print(f"      ✅ Can reach {server2['id']}")
                    results['passed'] += 1
                else:
                    print(f"      ❌ Cannot reach {server2['id']}")
                    results['failed'] += 1
                    results['issues'].append(f"{server1['id']} cannot reach {server2['id']}")
    
    # Results summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    total_tests = results['passed'] + results['failed']
    success_rate = (results['passed'] / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\nTests Passed: {results['passed']}/{total_tests}")
    print(f"Tests Failed: {results['failed']}/{total_tests}")
    print(f"Success Rate: {success_rate:.1f}%")
    
    if results['issues']:
        print(f"\n⚠️  ISSUES FOUND ({len(results['issues'])}):")
        for issue in results['issues']:
            print(f"  • {issue}")
    else:
        print(f"\n✅ ALL CONNECTIVITY TESTS PASSED!")
        print(f"Your multi-computer setup is ready to go!")
    
    print("\n" + "="*70)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Return exit code
    return 0 if results['failed'] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
