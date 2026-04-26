#!/usr/bin/env python3
import sys
import requests
import json
import time
from typing import List

NODES = [
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8002",
    "http://127.0.0.1:8003",
    "http://127.0.0.1:8004",
]

def clear_screen():
    print("\033[H\033[J", end="")

def print_header(title):
    print("=" * 60)
    print(f" {title.center(58)} ")
    print("=" * 60)

def get_input(prompt):
    try:
        return input(f"\n{prompt} > ").strip()
    except EOFError:
        sys.exit(0)

def select_node() -> str:
    print("\nSelect target Node:")
    for i, node in enumerate(NODES):
        print(f"[{i+1}] {node}")
    
    choice = get_input("Node [1-4]")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(NODES):
            return NODES[idx]
    except:
        pass
    return NODES[0]

def api_call(node, endpoint, method="POST", payload=None):
    url = f"{node}/api/v1/{endpoint}"
    try:
        if method == "POST":
            r = requests.post(url, json=payload, timeout=5)
        else:
            r = requests.get(url, timeout=5)
        
        try:
            response_json = r.json()
        except:
            response_json = {}

        if r.status_code >= 400:
            error_msg = response_json.get('detail', response_json.get('message', r.text))
            print(f"\n[!] Error {r.status_code}: {error_msg}")
            return None
        return response_json
    except Exception as e:
        print(f"\n[!] Connection Error: {e}")
        return None

def main_menu():
    node = NODES[0]
    while True:
        clear_screen()
        print_header("MOBILE MONEY INTERACTIVE CLIENT")
        print(f" Connected to: {node}")
        print("-" * 60)
        print(" [1] Create Account")
        print(" [2] Deposit (USSD)")
        print(" [3] Withdraw (USSD)")
        print(" [4] Check Balance (USSD)")
        print(" [5] Transfer (Direct API)")
        print(" [6] View System Status (Replication Check)")
        print(" [7] Switch Node")
        print(" [Q] Quit")
        
        choice = get_input("Select Action").upper()
        
        if choice == '1':
            phone = get_input("Phone Number (e.g. 0700000001)")
            name = get_input("Account Holder Name")
            amount = float(get_input("Initial Balance") or "0")
            res = api_call(node, "account/create", payload={
                "phone_number": phone,
                "account_holder_name": name,
                "initial_balance": amount
            })
            if res:
                msg = res.get('message', f"Account created for {res.get('phone_number')}")
                print(f"\n[+] Success: {msg}")
                if 'account_id' in res: print(f"    Account ID: {res['account_id']}")
            get_input("Press Enter to continue")

        elif choice == '2':
            phone = get_input("Phone Number")
            amount = get_input("Amount")
            ussd = f"*165*1*{phone}*{amount}#"
            res = api_call(node, "ussd", payload={"ussd_input": ussd})
            if res: print(f"\n[USSDR] {res['ussd_response']}")
            get_input("Press Enter to continue")

        elif choice == '3':
            phone = get_input("Phone Number")
            amount = get_input("Amount")
            ussd = f"*165*2*{phone}*{amount}#"
            res = api_call(node, "ussd", payload={"ussd_input": ussd})
            if res: print(f"\n[USSDR] {res['ussd_response']}")
            get_input("Press Enter to continue")

        elif choice == '4':
            phone = get_input("Phone Number")
            ussd = f"*165*3*{phone}#"
            res = api_call(node, "ussd", payload={"ussd_input": ussd})
            if res: print(f"\n[USSDR] {res['ussd_response']}")
            get_input("Press Enter to continue")

        elif choice == '5':
            from_phone = get_input("Sender Phone")
            to_phone = get_input("Receiver Phone")
            amount = float(get_input("Amount"))
            res = api_call(node, "operation/transfer", payload={
                "from_account_id": 1, # Demo assumes ID 1 for now or resolves by phone
                "from_phone_number": from_phone,
                "to_phone_number": to_phone,
                "amount": amount
            })
            if res:
                msg = res.get('message', 'Transfer processed')
                print(f"\n[+] Transfer: {msg}")
            get_input("Press Enter to continue")

        elif choice == '6':
            print("\nComparing balances across all nodes for phone...")
            phone = get_input("Phone Number to verify")
            print("-" * 30)
            for n in NODES:
                res = api_call(n, "operation/balance", payload={"phone_number": phone})
                if res and res['status'] == 'success':
                    print(f" {n:25} | {res['data']['balance']:>10} KES")
                else:
                    print(f" {n:25} | OFFLINE/NOT FOUND")
            get_input("\nPress Enter to continue")

        elif choice == '7':
            node = select_node()

        elif choice == 'Q':
            break

if __name__ == "__main__":
    main_menu()
