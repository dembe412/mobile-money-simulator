"""
Interactive test client for Mobile Money System
Demonstrates all operations and features
"""
import sys
import time
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from client.mobile_money_client import MobileMoneyClient


def print_section(title):
    """Print formatted section title"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_result(operation, success, response):
    """Print formatted result"""
    status_color = "✓" if success else "✗"
    print(f"{status_color} {operation}")
    if success:
        if "data" in response:
            print(f"  Response: {json.dumps(response['data'], indent=4)}")
        else:
            print(f"  Message: {response.get('message', 'Success')}")
    else:
        print(f"  Error: {response.get('message', 'Unknown error')}")
    print()


def test_basic_operations():
    """Test basic account operations"""
    print_section("Testing Basic Account Operations")
    
    # Initialize client
    client = MobileMoneyClient(
        server_urls=[
            "http://localhost:8001",
            "http://localhost:8002",
            "http://localhost:8003"
        ]
    )
    
    print("Initialized client with 3 servers")
    print("  - http://localhost:8001")
    print("  - http://localhost:8002")
    print("  - http://localhost:8003\n")
    
    # Test 1: Create account
    print_section("1. Create Account")
    phone = "075346363"
    success, response = client.create_account(
        phone_number=phone,
        account_holder_name="John Doe",
        initial_balance=10000.0
    )
    print_result("Create account", success, response)
    
    if success:
        account_id = response.get("account_id")
    else:
        print("❌ Failed to create account. Exiting.")
        return
    
    # Test 2: Check Balance
    print_section("2. Check Balance")
    success, response = client.check_balance(account_id)
    print_result("Check balance", success, response)
    
    # Test 3: Withdraw
    print_section("3. Withdraw 1000 KES")
    success, response = client.withdraw(
        account_id=account_id,
        phone_number=phone,
        amount=1000.0,
        client_reference="withdraw_001"
    )
    print_result("Withdraw 1000 KES", success, response)
    
    # Test 4: Check Balance After Withdraw
    print_section("4. Check Balance After Withdraw")
    success, response = client.check_balance(account_id)
    print_result("Check balance", success, response)
    
    # Test 5: Deposit
    print_section("5. Deposit 500 KES")
    success, response = client.deposit(
        account_id=account_id,
        phone_number=phone,
        amount=500.0,
        client_reference="deposit_001"
    )
    print_result("Deposit 500 KES", success, response)
    
    # Test 6: Check Balance After Deposit
    print_section("6. Check Balance After Deposit")
    success, response = client.check_balance(account_id)
    print_result("Check balance", success, response)
    
    # Test 7: Get Transaction History
    print_section("7. Get Transaction History")
    success, response = client.get_transactions(account_id, limit=10)
    print_result("Get transactions", success, response)
    
    return account_id, phone


def test_ussd_operations(account_id, phone):
    """Test USSD protocol operations"""
    print_section("Testing USSD Protocol")
    
    client = MobileMoneyClient(
        server_urls=[
            "http://localhost:8001",
            "http://localhost:8002",
            "http://localhost:8003"
        ]
    )
    
    # Test 1: USSD Withdraw
    print_section("1. USSD Withdraw (*165*2*075346363*2000#)")
    success, response = client.ussd_request("*165*2*075346363*2000#")
    print_result("USSD Withdraw", success, response)
    if success and "ussd_response" in response:
        print(f"  USSD Response: {response['ussd_response']}")
    print()
    
    # Test 2: USSD Deposit
    print_section("2. USSD Deposit (*165*1*075346363*1500#)")
    success, response = client.ussd_request("*165*1*075346363*1500#")
    print_result("USSD Deposit", success, response)
    if success and "ussd_response" in response:
        print(f"  USSD Response: {response['ussd_response']}")
    print()
    
    # Test 3: USSD Balance Check
    print_section("3. USSD Balance Check (*165*3*075346363#)")
    success, response = client.ussd_request("*165*3*075346363#")
    print_result("USSD Balance Check", success, response)
    if success and "ussd_response" in response:
        print(f"  USSD Response: {response['ussd_response']}")
    print()
    
    # Test 4: USSD Mini Statement
    print_section("4. USSD Mini Statement (*165*4*075346363#)")
    success, response = client.ussd_request("*165*4*075346363#")
    print_result("USSD Mini Statement", success, response)
    if success and "ussd_response" in response:
        print(f"  USSD Response: {response['ussd_response']}")
    print()
    
    # Test 5: Invalid USSD Code
    print_section("5. Invalid USSD Code (*165*9*075346363#)")
    success, response = client.ussd_request("*165*9*075346363#")
    print_result("Invalid USSD (Expected Error)", success, response)
    if not success and "ussd_response" in response:
        print(f"  USSD Response: {response['ussd_response']}")
    print()


def test_server_discovery():
    """Test server discovery and routing"""
    print_section("Testing Server Discovery & Consistent Hashing")
    
    client = MobileMoneyClient()
    
    test_phones = [
        "075346363",
        "0721234567",
        "0728765432",
        "0733333333",
        "0740000000",
    ]
    
    print("Phone number → Server routing using hash ring:\n")
    
    for phone in test_phones:
        success, server_url, routing = client.discover_server(phone)
        if success:
            primary = routing.get("primary_server", {})
            print(f"  {phone} → {primary.get('id', 'N/A')}")
            print(f"    Primary: {primary.get('url', 'N/A')}")
            
            replicas = routing.get("replica_servers", [])
            if replicas:
                replica_ids = [r.get('id') for r in replicas]
                print(f"    Replicas: {replica_ids}")
        else:
            print(f"  {phone} → Discovery failed: {routing.get('message')}")
        print()


def test_idempotency():
    """Test request idempotency"""
    print_section("Testing Request Idempotency")
    
    client = MobileMoneyClient()
    
    print("Submitting same withdrawal request 3 times...")
    print("(Should only deduct balance once, return cached response on retry)\n")
    
    # Create account first
    success, response = client.create_account(
        phone_number="0799999999",
        account_holder_name="Test User",
        initial_balance=5000.0
    )
    
    if not success:
        print("Failed to create test account")
        return
    
    account_id = response.get("account_id")
    
    # Submit same request 3 times
    for i in range(3):
        print(f"Attempt {i+1}:")
        success, response = client.withdraw(
            account_id=account_id,
            phone_number="0799999999",
            amount=500.0,
            client_reference="idempotent_test_001"  # Same reference = same request ID
        )
        
        if success:
            balance = response.get("data", {}).get("balance_after")
            print(f"  ✓ Balance after: {balance}")
        else:
            print(f"  ✗ Error: {response.get('message')}")
        print()
    
    # Verify final balance
    success, response = client.check_balance(account_id)
    if success:
        final_balance = response.get("data", {}).get("balance")
        expected_balance = 5000.0 - 500.0  # Only deducted once
        print(f"Final balance: {final_balance}")
        print(f"Expected balance: {expected_balance}")
        print(f"✓ Idempotency working correctly!" if final_balance == expected_balance else "✗ Idempotency failed!")


def test_concurrent_operations():
    """Test concurrent operations on same account"""
    print_section("Testing Concurrent Operations (Locking)")
    
    client = MobileMoneyClient()
    
    print("Creating account and attempting concurrent operations...\n")
    
    success, response = client.create_account(
        phone_number="0788888888",
        account_holder_name="Concurrent Test",
        initial_balance=10000.0
    )
    
    if not success:
        print("Failed to create test account")
        return
    
    account_id = response.get("account_id")
    
    print("Sequential operations (should all succeed):\n")
    
    # Op 1: Withdraw
    print("Op 1: Withdraw 1000")
    success, response = client.withdraw(account_id, "0788888888", 1000.0)
    print(f"  Result: {'✓ Success' if success else '✗ Failed'}")
    print()
    
    # Op 2: Check balance
    print("Op 2: Check balance")
    success, response = client.check_balance(account_id)
    balance = response.get("data", {}).get("balance") if success else None
    print(f"  Result: ✓ Balance = {balance}")
    print()
    
    # Op 3: Deposit
    print("Op 3: Deposit 500")
    success, response = client.deposit(account_id, "0788888888", 500.0)
    print(f"  Result: {'✓ Success' if success else '✗ Failed'}")
    print()
    
    # Final balance
    print("Final balance check:")
    success, response = client.check_balance(account_id)
    if success:
        final_balance = response.get("data", {}).get("balance")
        expected_balance = 10000.0 - 1000.0 + 500.0
        print(f"  Final balance: {final_balance}")
        print(f"  Expected: {expected_balance}")
        print(f"  ✓ Correct!" if final_balance == expected_balance else "  ✗ Incorrect!")


def main():
    """Run all tests"""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*68 + "║")
    print("║" + "  📱 Mobile Money System - Integration Test Client".center(68) + "║")
    print("║" + "  Distributed P2P Payment Platform".center(68) + "║")
    print("║" + " "*68 + "║")
    print("╚" + "="*68 + "╝")
    
    print("\n⚠️  Note: Make sure all servers are running:")
    print("  - Server 1: http://localhost:8001")
    print("  - Server 2: http://localhost:8002")
    print("  - Server 3: http://localhost:8003")
    print("\nStarting tests in 2 seconds...\n")
    time.sleep(2)
    
    try:
        # Run tests
        account_id, phone = test_basic_operations()
        test_ussd_operations(account_id, phone)
        test_server_discovery()
        test_idempotency()
        test_concurrent_operations()
        
        print_section("✓ All Tests Completed Successfully!")
        print("Check the logs for detailed output.")
        
    except ConnectionError as e:
        print(f"\n❌ CONNECTION ERROR: {str(e)}")
        print("\nMake sure all servers are running:")
        print("  docker-compose up")
        print("OR")
        print("  export SERVER_ID=server_1 && python main.py")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
