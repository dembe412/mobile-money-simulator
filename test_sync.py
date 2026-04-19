#!/usr/bin/env python3
"""
Comprehensive test to verify all operations are synchronized with the database
"""
import requests
import json

def main():
    print('=' * 70)
    print('COMPREHENSIVE OPERATION SYNC TEST')
    print('=' * 70)

    # Test 1: Create multiple accounts
    print('\n--- Test 1: Create Multiple Accounts ---')
    accounts = []
    phone_numbers = ['254788888888', '254799999999', '254711111111']

    for i, phone in enumerate(phone_numbers):
        data = {
            'phone_number': phone,
            'account_holder_name': f'TestUser{i+1}',
            'initial_balance': 5000 * (i + 1)
        }
        response = requests.post('http://localhost:8001/api/v1/account/create', json=data)
        if response.status_code == 200:
            acc = response.json()
            accounts.append(acc)
            print(f'Created account {acc["account_id"]}: {phone} with balance {acc["balance"]}')
        else:
            print(f'Failed to create account for {phone}: {response.text}')

    # Test 2: Deposit operations
    print('\n--- Test 2: Multiple Deposits ---')
    for account in accounts:
        phone = account['phone_number']
        amount = 1000
        data = {
            'phone_number': phone,
            'amount': amount,
            'client_reference': f'test-deposit-{phone}'
        }
        response = requests.post('http://localhost:8001/api/v1/operation/deposit', json=data)
        if response.status_code == 200:
            result = response.json()
            print(f'Deposited {amount} to {phone}: New balance = {result["data"]["balance_after"]}')
        else:
            print(f'Deposit failed for {phone}')

    # Test 3: Withdraw operations
    print('\n--- Test 3: Multiple Withdrawals ---')
    for account in accounts:
        phone = account['phone_number']
        amount = 500
        data = {
            'phone_number': phone,
            'amount': amount,
            'client_reference': f'test-withdraw-{phone}'
        }
        response = requests.post('http://localhost:8001/api/v1/operation/withdraw', json=data)
        if response.status_code == 200:
            result = response.json()
            print(f'Withdrew {amount} from {phone}: New balance = {result["data"]["balance_after"]}')
        else:
            print(f'Withdrawal failed for {phone}')

    # Test 4: Verify final balances (calculated)
    print('\n--- Test 4: Verify Expected vs Actual Balances ---')
    expected_balances = {}
    for i, account in enumerate(accounts):
        phone = account['phone_number']
        # initial + deposit - withdrawal
        expected = (5000 * (i + 1)) + 1000 - 500
        expected_balances[phone] = expected
        print(f'Expected balance for {phone}: {expected}')

    # Test 5: Check actual balances via GET endpoint
    print('\n--- Test 5: Verify Balances (GET /api/v1/operation/balance/{id}) ---')
    all_match = True
    for account in accounts:
        phone = account['phone_number']
        account_id = account['account_id']
        
        response = requests.get(f'http://localhost:8001/api/v1/operation/balance/{account_id}')
        if response.status_code == 200:
            actual_balance = response.json()['data']['balance']
            expected = expected_balances[phone]
            match = actual_balance == expected
            status = 'PASS' if match else 'FAIL'
            print(f'[{status}] {phone} (ID {account_id}): Expected={expected}, Actual={actual_balance}')
            if not match:
                all_match = False
        else:
            print(f'[FAIL] Failed to fetch balance for {phone}')
            all_match = False

    # Test 6: Check via POST with phone
    print('\n--- Test 6: Verify Balances (POST /api/v1/operation/balance) ---')
    for account in accounts:
        phone = account['phone_number']
        data = {'phone_number': phone}
        response = requests.post('http://localhost:8001/api/v1/operation/balance', json=data)
        if response.status_code == 200:
            actual_balance = response.json()['data']['balance']
            expected = expected_balances[phone]
            match = actual_balance == expected
            status = 'PASS' if match else 'FAIL'
            print(f'[{status}] {phone}: Expected={expected}, Actual={actual_balance}')
            if not match:
                all_match = False
        else:
            print(f'[FAIL] Failed to fetch balance for {phone}')
            all_match = False

    # Test 7: Verify account details match
    print('\n--- Test 7: Verify Account Details Consistency ---')
    for account in accounts:
        account_id = account['account_id']
        phone = account['phone_number']
        
        response = requests.get(f'http://localhost:8001/api/v1/account/{account_id}')
        if response.status_code == 200:
            details = response.json()
            stored_phone = details['phone_number']
            match = stored_phone == phone
            status = 'PASS' if match else 'FAIL'
            print(f'[{status}] Account {account_id}: Phone {phone} matches stored {stored_phone}')
            if not match:
                all_match = False
        else:
            print(f'[FAIL] Failed to fetch account {account_id}')
            all_match = False

    print('\n' + '=' * 70)
    if all_match:
        print('SUCCESS: All operations are in sync with the database')
    else:
        print('FAILURE: There are sync issues with some operations')
    print('=' * 70)

if __name__ == '__main__':
    main()
