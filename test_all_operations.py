#!/usr/bin/env python3
"""
Test all API operations to ensure they work correctly
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import requests
import json
import time
from decimal import Decimal

BASE_URL = "http://localhost:8001"

def test_health():
    """Test health endpoint"""
    print("\n" + "="*80)
    print("TEST: Health Check")
    print("="*80)
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_status():
    """Test server status endpoint"""
    print("\n" + "="*80)
    print("TEST: Server Status")
    print("="*80)
    try:
        response = requests.get(f"{BASE_URL}/status")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_create_account():
    """Test account creation"""
    print("\n" + "="*80)
    print("TEST: Create Account")
    print("="*80)
    try:
        payload = {
            "phone_number": "0799999999",
            "account_holder_name": "Test User",
            "initial_balance": 1000000
        }
        response = requests.post(f"{BASE_URL}/api/v1/account/create", json=payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            data = response.json()
            return True, data.get('account_id')
        return False, None
    except Exception as e:
        print(f"ERROR: {e}")
        return False, None

def test_get_account(account_id):
    """Test get account details"""
    print("\n" + "="*80)
    print(f"TEST: Get Account {account_id}")
    print("="*80)
    try:
        response = requests.get(f"{BASE_URL}/api/v1/account/{account_id}")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_deposit(account_id):
    """Test deposit operation"""
    print("\n" + "="*80)
    print("TEST: Deposit Operation")
    print("="*80)
    try:
        payload = {
            "account_id": account_id,
            "phone_number": "0799999999",
            "amount": 50000
        }
        response = requests.post(f"{BASE_URL}/api/v1/operation/deposit", json=payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_withdraw(account_id):
    """Test withdraw operation"""
    print("\n" + "="*80)
    print("TEST: Withdraw Operation")
    print("="*80)
    try:
        payload = {
            "account_id": account_id,
            "phone_number": "0799999999",
            "amount": 25000
        }
        response = requests.post(f"{BASE_URL}/api/v1/operation/withdraw", json=payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_balance_post(account_id):
    """Test balance check via POST"""
    print("\n" + "="*80)
    print("TEST: Balance Check (POST)")
    print("="*80)
    try:
        payload = {
            "account_id": account_id
        }
        response = requests.post(f"{BASE_URL}/api/v1/operation/balance", json=payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_balance_get(account_id):
    """Test balance check via GET"""
    print("\n" + "="*80)
    print("TEST: Balance Check (GET)")
    print("="*80)
    try:
        response = requests.get(f"{BASE_URL}/api/v1/operation/balance/{account_id}")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_transactions(account_id):
    """Test get transactions"""
    print("\n" + "="*80)
    print("TEST: Get Transactions")
    print("="*80)
    try:
        response = requests.get(f"{BASE_URL}/api/v1/operation/transactions/{account_id}?limit=5")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_transfer(from_account_id):
    """Test transfer operation"""
    print("\n" + "="*80)
    print("TEST: Transfer Operation")
    print("="*80)
    try:
        payload = {
            "from_account_id": from_account_id,
            "from_phone_number": "0799999999",
            "to_phone_number": "0752235731",  # From seeded data
            "amount": 10000
        }
        response = requests.post(f"{BASE_URL}/api/v1/operation/transfer", json=payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_ussd():
    """Test USSD gateway"""
    print("\n" + "="*80)
    print("TEST: USSD Gateway")
    print("="*80)
    try:
        payload = {
            "ussd_input": "*165*1*0752235731*1*100000#",
            "phone_number": "0752235731",
            "session_id": "test_session_123"
        }
        response = requests.post(f"{BASE_URL}/api/v1/ussd", json=payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("MOBILE MONEY API - COMPREHENSIVE OPERATION TEST")
    print("="*80)
    
    results = {}
    
    # Test health
    results['health'] = test_health()
    time.sleep(0.5)
    
    # Test status
    results['status'] = test_status()
    time.sleep(0.5)
    
    # Test account creation
    success, account_id = test_create_account()
    results['create_account'] = success
    time.sleep(0.5)
    
    if account_id:
        # Test get account
        results['get_account'] = test_get_account(account_id)
        time.sleep(0.5)
        
        # Test deposit
        results['deposit'] = test_deposit(account_id)
        time.sleep(0.5)
        
        # Test balance (POST)
        results['balance_post'] = test_balance_post(account_id)
        time.sleep(0.5)
        
        # Test balance (GET)
        results['balance_get'] = test_balance_get(account_id)
        time.sleep(0.5)
        
        # Test withdraw
        results['withdraw'] = test_withdraw(account_id)
        time.sleep(0.5)
        
        # Test transactions
        results['transactions'] = test_transactions(account_id)
        time.sleep(0.5)
        
        # Test transfer
        results['transfer'] = test_transfer(account_id)
        time.sleep(0.5)
    
    # Test USSD
    results['ussd'] = test_ussd()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {test_name:30} {status}")
    
    total = len(results)
    passed = sum(1 for r in results.values() if r)
    
    print("-"*80)
    print(f"  Total: {passed}/{total} tests passed")
    print("="*80)
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
