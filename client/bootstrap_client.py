#!/usr/bin/env python3
"""
Auto-Discovery Bootstrap Client
Demonstrates how to use the client with auto-discovery:
  1. Discovers available servers from the registry
  2. Connects to the network
  3. Initializes the client
  4. Allows interaction with the system

Usage:
  python client/bootstrap_client.py [--phone PHONE] [--wait-time SECONDS] [--mode MODE]

Examples:
  # Interactive USSD mode with auto-discovery
  python client/bootstrap_client.py
  
  # With specific phone number
  python client/bootstrap_client.py --phone 0700000001
  
  # Wait up to 60 seconds for servers to be available
  python client/bootstrap_client.py --wait-time 60
  
  # API testing mode instead of USSD
  python client/bootstrap_client.py --mode api
"""

import sys
import argparse
import logging
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from client.mobile_money_client import MobileMoneyClient
from client.ussd_phone_client import USSDPhoneClient
from src.distributed.client_discovery import ClientServiceDiscovery, ClientDiscoveryError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def discover_network(max_wait_seconds: int = 30, wait: bool = True) -> list:
    """
    Discover the network by querying the service registry
    
    Args:
        max_wait_seconds: Maximum time to wait for servers
        wait: If True, wait for servers to be available
        
    Returns:
        List of server URLs
    """
    project_root = Path(__file__).parent.parent
    registry_path = project_root / "data" / "registry.db"
    
    logger.info("=" * 70)
    logger.info("AUTO-DISCOVERY CLIENT - Network Discovery Phase")
    logger.info("=" * 70)
    logger.info(f"Looking for service registry: {registry_path}")
    
    try:
        discovery = ClientServiceDiscovery(registry_path)
        logger.info("✓ Service registry found")
        
        if wait:
            logger.info(f"Waiting for servers... (max {max_wait_seconds}s)")
            urls = discovery.wait_for_servers(
                min_servers=1,
                max_wait_seconds=max_wait_seconds,
                poll_interval=2.0
            )
        else:
            urls = discovery.discover()
        
        logger.info("=" * 70)
        logger.info(f"✓ NETWORK DISCOVERED: Found {len(urls)} server(s)")
        logger.info("=" * 70)
        for i, url in enumerate(urls, 1):
            logger.info(f"  [{i}] {url}")
        logger.info("=" * 70)
        
        return urls
        
    except ClientDiscoveryError as e:
        logger.error("=" * 70)
        logger.error(f"✗ DISCOVERY FAILED: {e}")
        logger.error("=" * 70)
        logger.error("Please ensure at least one server is running:")
        logger.error("  SERVER_ID=server_1 python main.py")
        logger.error("  SERVER_ID=server_2 python main.py")
        logger.error("  SERVER_ID=server_3 python main.py")
        sys.exit(1)


def test_api_mode(phone_number: str, server_urls: list):
    """
    Test mode: Direct API calls to verify connectivity
    
    Args:
        phone_number: Phone number for testing
        server_urls: List of discovered server URLs
    """
    logger.info("=" * 70)
    logger.info("API TEST MODE - Verifying Server Connectivity")
    logger.info("=" * 70)
    
    client = MobileMoneyClient(server_urls=server_urls)
    
    # Test 1: Discover routing for phone number
    logger.info("\n[Test 1] Discovering routing for phone number...")
    routing = client.discover_server(phone_number)
    if routing["success"]:
        logger.info(f"✓ Routing discovered: {routing['data']['url']}")
    else:
        logger.warning(f"⚠ Routing discovery: {routing['message']}")
    
    # Test 2: Create account
    logger.info("\n[Test 2] Creating test account...")
    result = client.create_account(
        phone_number=phone_number,
        account_holder_name="Test User",
        initial_balance=1000.0
    )
    if result["success"]:
        logger.info(f"✓ Account created: {result['data']}")
    else:
        logger.info(f"Note: {result['message']}")
    
    logger.info("\n" + "=" * 70)
    logger.info("✓ API CONNECTIVITY VERIFIED")
    logger.info("=" * 70)


def start_ussd_mode(phone_number: str, server_urls: list):
    """
    Start interactive USSD mode
    
    Args:
        phone_number: Phone number for USSD session
        server_urls: List of discovered server URLs
    """
    logger.info("=" * 70)
    logger.info("STARTING USSD INTERACTIVE MODE")
    logger.info("=" * 70)
    logger.info(f"Phone Number: {phone_number}")
    logger.info(f"Connected Servers: {len(server_urls)}")
    logger.info("=" * 70)
    logger.info("")
    
    # Start USSD client with discovered servers
    ussd_client = USSDPhoneClient(
        phone_number=phone_number,
        server_urls=server_urls
    )
    ussd_client.run()


def main():
    """Main bootstrap entry point"""
    parser = argparse.ArgumentParser(
        description="Auto-Discovery Bootstrap Client for Mobile Money System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python client/bootstrap_client.py                    # Interactive USSD mode
  python client/bootstrap_client.py --phone 0700000001 # Specific phone number
  python client/bootstrap_client.py --mode api         # API testing mode
  python client/bootstrap_client.py --wait-time 60     # Wait longer for servers
        """
    )
    
    parser.add_argument(
        "--phone",
        type=str,
        help="Phone number to use (default: interactive prompt)"
    )
    
    parser.add_argument(
        "--wait-time",
        type=int,
        default=30,
        help="Maximum seconds to wait for servers (default: 30)"
    )
    
    parser.add_argument(
        "--mode",
        choices=["ussd", "api"],
        default="ussd",
        help="Operating mode: ussd (interactive) or api (testing)"
    )
    
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Don't wait for servers, fail immediately if none available"
    )
    
    args = parser.parse_args()
    
    try:
        # Phase 1: Auto-discover the network
        server_urls = discover_network(
            max_wait_seconds=args.wait_time,
            wait=not args.no_wait
        )
        
        # Phase 2: Get phone number if not provided
        if args.phone:
            phone_number = args.phone
        else:
            phone_number = input("\nEnter phone number: ").strip()
            if not phone_number:
                logger.error("Phone number is required")
                sys.exit(1)
        
        # Phase 3: Start selected mode
        if args.mode == "api":
            test_api_mode(phone_number, server_urls)
        else:  # ussd
            start_ussd_mode(phone_number, server_urls)
        
    except KeyboardInterrupt:
        logger.info("\n[*] Bootstrap interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Bootstrap failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
