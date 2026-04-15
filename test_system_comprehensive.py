"""
Comprehensive System Test Suite
Tests all components: Client, Protocol, Operations, Hashing
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import all modules we want to test
from src.models import Account, Transaction, Request as DBRequest, AccountLock, ReplicationLogEntry
from src.core.idempotency import generate_request_id, USSDRequest
from src.distributed.hashing import ConsistentHash, Node
from src.ussd.protocol import USSDParser, USSDFormatter, USSDRequest as Protocol_USSDRequest
from client.mobile_money_client import MobileMoneyClient, Request


class TestResults:
    """Track test results"""
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self, test_name: str):
        self.total += 1
        self.passed += 1
        print(f"✅ {test_name}")
    
    def add_fail(self, test_name: str, reason: str):
        self.total += 1
        self.failed += 1
        self.errors.append((test_name, reason))
        print(f"❌ {test_name}: {reason}")
    
    def summary(self):
        print(f"\n{'='*60}")
        print(f"TEST SUMMARY: {self.passed}/{self.total} passed")
        print(f"{'='*60}")
        if self.errors:
            print("\nFailed Tests:")
            for test_name, reason in self.errors:
                print(f"  - {test_name}")
                print(f"    Reason: {reason}")
        return self.failed == 0


class SystemTests:
    """Run all system tests"""
    
    def __init__(self):
        self.results = TestResults()
    
    def test_idempotency_system(self):
        """Test request ID generation and idempotency"""
        print("\n" + "="*60)
        print("1. TESTING IDEMPOTENCY SYSTEM")
        print("="*60)
        
        try:
            # Test request ID generation
            req_id_1 = generate_request_id("server_1", "075346363")
            req_id_2 = generate_request_id("server_1", "075346363")
            
            # IDs should be unique even for same inputs
            if req_id_1 != req_id_2:
                self.results.add_pass("Request ID generation - Unique IDs created")
            else:
                self.results.add_fail("Request ID generation", "Generated identical IDs")
            
            # Check format: {server_id}_{timestamp_ms}_{uuid}_{phone}
            parts = req_id_1.split("_")
            if len(parts) >= 3 and parts[0] == "server_1" and parts[3] == "075346363":
                self.results.add_pass("Request ID format - Correct structure")
            else:
                self.results.add_fail("Request ID format", f"Unexpected format: {req_id_1}")
            
            # Test USSD request tracking
            ussd_req = USSDRequest(
                phone_number="075346363",
                ussd_input="*165*1*075346363*5000",
                server_id="server_1"
            )
            
            if ussd_req.phone_number == "075346363" and ussd_req.server_id == "server_1":
                self.results.add_pass("USSD request tracking - Object created correctly")
            else:
                self.results.add_fail("USSD request tracking", "Invalid object structure")
        
        except Exception as e:
            self.results.add_fail("Idempotency system", str(e))
    
    def test_consistent_hashing(self):
        """Test distributed server discovery"""
        print("\n" + "="*60)
        print("2. TESTING CONSISTENT HASHING")
        print("="*60)
        
        try:
            # Create hash ring with 3 servers
            servers = [
                Node("server_1", "localhost:8001"),
                Node("server_2", "localhost:8002"),
                Node("server_3", "localhost:8003")
            ]
            
            hash_ring = ConsistentHash()
            for server in servers:
                hash_ring.add_node(server)
            
            if len(hash_ring.nodes) == 3:
                self.results.add_pass("Hash ring initialization - 3 servers added")
            else:
                self.results.add_fail("Hash ring initialization", f"Got {len(hash_ring.nodes)} servers")
            
            # Test consistent hashing for phone numbers
            phone_nums = ["075346363", "0712345678", "0798765432"]
            assignments = {}
            
            for phone in phone_nums:
                node = hash_ring.get_node(phone)
                if node:
                    assignments[phone] = node.server_id
                else:
                    self.results.add_fail("Node assignment", f"No node for {phone}")
                    return
            
            self.results.add_pass("Node assignment - All phones routed")
            
            # Test consistency: same phone always routes to same server
            node1 = hash_ring.get_node("075346363").server_id
            node2 = hash_ring.get_node("075346363").server_id
            
            if node1 == node2:
                self.results.add_pass("Routing consistency - Same phone → same server")
            else:
                self.results.add_fail("Routing consistency", "Phone routed to different servers")
            
            # Test virtual nodes (should have 150 per server)
            expected_vnodes = 3 * 150  # 3 servers * 150 vnodes
            actual_vnodes = len(hash_ring.ring)
            
            if actual_vnodes == expected_vnodes:
                self.results.add_pass(f"Virtual nodes - {actual_vnodes} vnodes created")
            else:
                self.results.add_fail("Virtual nodes", f"Expected {expected_vnodes}, got {actual_vnodes}")
            
            # Test node removal and re-routing
            hash_ring.remove_node(servers[0])
            phone_after_removal = hash_ring.get_node("075346363")
            
            if phone_after_removal and phone_after_removal.server_id != "server_1":
                self.results.add_pass("Node removal - Requests re-routed successfully")
            else:
                self.results.add_fail("Node removal", "Request still routed to removed server")
        
        except Exception as e:
            self.results.add_fail("Consistent hashing", str(e))
    
    def test_ussd_protocol(self):
        """Test USSD protocol parsing and formatting"""
        print("\n" + "="*60)
        print("3. TESTING USSD PROTOCOL")
        print("="*60)
        
        try:
            # Test parsing valid USSD codes
            test_codes = [
                {
                    "code": "*165*1*075346363*5000#",
                    "expected_op": "deposit",
                    "expected_amount": 5000
                },
                {
                    "code": "*165*2*075346363*2000#",
                    "expected_op": "withdraw",
                    "expected_amount": 2000
                },
                {
                    "code": "*165*3*075346363*#",
                    "expected_op": "check_balance",
                    "expected_amount": None
                }
            ]
            
            parser = USSDParser()
            
            for test in test_codes:
                try:
                    result = parser.parse(test["code"])
                    
                    if result and result.get("operation") == test["expected_op"]:
                        self.results.add_pass(f"USSD parsing - {test['expected_op']} code parsed")
                    else:
                        self.results.add_fail(
                            f"USSD parsing - {test['expected_op']}",
                            f"Got: {result}"
                        )
                except Exception as e:
                    self.results.add_fail(f"USSD parsing - {test['code']}", str(e))
            
            # Test USSD response formatting
            formatter = USSDFormatter()
            response = formatter.format_menu(
                title="MAIN MENU",
                options={
                    "1": "Deposit",
                    "2": "Withdraw",
                    "3": "Balance"
                }
            )
            
            if response and "MAIN MENU" in response and "Deposit" in response:
                self.results.add_pass("USSD formatting - Menu formatted correctly")
            else:
                self.results.add_fail("USSD formatting", "Missing menu content")
            
            # Test error response
            error_response = formatter.format_error("Insufficient balance")
            
            if error_response and "error" in error_response.lower():
                self.results.add_pass("USSD error response - Error formatted")
            else:
                self.results.add_fail("USSD error response", "Invalid error format")
        
        except Exception as e:
            self.results.add_fail("USSD protocol", str(e))
    
    def test_client_library(self):
        """Test client library structure and methods"""
        print("\n" + "="*60)
        print("4. TESTING CLIENT LIBRARY")
        print("="*60)
        
        try:
            # Test client initialization
            client = MobileMoneyClient(base_url="http://localhost:8001")
            
            if client.server_urls and client.server_urls[0] == "http://localhost:8001":
                self.results.add_pass("Client initialization - Configured correctly")
            else:
                self.results.add_fail("Client initialization", "Invalid configuration")
            
            # Test request signing
            request = Request("test_req_id_123")
            request.add_param("amount", 5000)
            signature = request.sign("secret-key")
            
            if signature and len(signature) == 64:  # SHA256 hex is 64 chars
                self.results.add_pass("Request signing - Valid HMAC signature generated")
            else:
                self.results.add_fail("Request signing", f"Invalid signature: {signature}")
            
            # Test method availability
            required_methods = [
                'discover_server',
                'create_account',
                'deposit',
                'withdraw',
                'check_balance',
                'get_transaction_history',
                'get_account_details',
                'ussd_request'
            ]
            
            for method in required_methods:
                if hasattr(client, method) and callable(getattr(client, method)):
                    self.results.add_pass(f"Client methods - {method}() available")
                else:
                    self.results.add_fail(f"Client methods - {method}", "Method not found")
        
        except Exception as e:
            self.results.add_fail("Client library", str(e))
    
    def test_models(self):
        """Test SQLAlchemy models"""
        print("\n" + "="*60)
        print("5. TESTING DATA MODELS")
        print("="*60)
        
        try:
            # Check if models are defined
            models_to_check = [
                ("Account", Account),
                ("Transaction", Transaction),
                ("DBRequest", DBRequest),
                ("AccountLock", AccountLock),
                ("ReplicationLogEntry", ReplicationLogEntry)
            ]
            
            for name, model_class in models_to_check:
                if model_class:
                    self.results.add_pass(f"Models - {name} model defined")
                else:
                    self.results.add_fail(f"Models - {name}", "Model not found")
            
            # Check model attributes
            account_attrs = ["account_id", "phone_number", "balance"]
            
            for attr in account_attrs:
                if hasattr(Account, attr):
                    self.results.add_pass(f"Model attributes - Account.{attr} defined")
                else:
                    self.results.add_fail(f"Model attributes - Account.{attr}", "Attribute missing")
        
        except Exception as e:
            self.results.add_fail("Models", str(e))
    
    def test_configuration(self):
        """Test configuration loading"""
        print("\n" + "="*60)
        print("6. TESTING CONFIGURATION")
        print("="*60)
        
        try:
            from config.settings import AppConfig
            
            # Test config initialization
            config = AppConfig()
            
            if config.SERVER_HOST and config.SERVER_PORT:
                self.results.add_pass(f"Config - Server: {config.SERVER_HOST}:{config.SERVER_PORT}")
            else:
                self.results.add_fail("Config", "Missing server configuration")
            
            if config.DATABASE_URL:
                self.results.add_pass("Config - Database URL configured")
            else:
                self.results.add_fail("Config", "Missing database configuration")
            
            if config.REDIS_URL:
                self.results.add_pass("Config - Redis URL configured")
            else:
                self.results.add_fail("Config", "Missing Redis configuration")
        
        except Exception as e:
            self.results.add_fail("Configuration", str(e))
    
    def run_all_tests(self):
        """Run all test suites"""
        print("\n")
        print("#" * 60)
        print("# MOBILE MONEY SYSTEM - COMPREHENSIVE TEST SUITE")
        print("#" * 60)
        print(f"# Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("#" * 60)
        
        self.test_idempotency_system()
        self.test_consistent_hashing()
        self.test_ussd_protocol()
        self.test_client_library()
        self.test_models()
        self.test_configuration()
        
        return self.results.summary()


def main():
    """Run all tests"""
    tester = SystemTests()
    success = tester.run_all_tests()
    
    if success:
        print("\n✅ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {tester.results.failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
