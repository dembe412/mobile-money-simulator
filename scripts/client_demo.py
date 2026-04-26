#!/usr/bin/env python3
"""
client_demo.py — 3-Client Simulation
====================================
A simple script to demonstrate concurrent client interactions.
It simulates Alice, Bob, and Carol doing transactions across all 3 nodes.

Usage:
  python scripts/client_demo.py
"""
import sys
import os
import time
import requests
import uuid
from decimal import Decimal

# Nodes
NODES = [
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8002",
    "http://127.0.0.1:8003",
]

def request(node_idx: int, method: str, endpoint: str, payload: dict = None):
    url = f"{NODES[node_idx]}/api/v1/{endpoint}"
    try:
        if method == "POST":
            r = requests.post(url, json=payload, timeout=5)
        else:
            r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error calling {url}: {e}")
        return None

def main():
    print("Checking if nodes are alive...")
    alive = sum(1 for n in range(3) if request(n, "GET", "../health") is not None)
    if alive < 3:
        print(f"Only {alive}/3 nodes are responding. Start all 3 terminals first!")
        sys.exit(1)
        
    print("\n--- Creating Accounts ---")
    request(0, "POST", "account/create", {
        "phone_number": "0700000001",
        "account_holder_name": "Alice Mwangi",
        "initial_balance": 50000
    })
    request(1, "POST", "account/create", {
        "phone_number": "0700000002",
        "account_holder_name": "Bob Kamau",
        "initial_balance": 50000
    })
    request(2, "POST", "account/create", {
        "phone_number": "0700000003",
        "account_holder_name": "Carol Wanjiru",
        "initial_balance": 50000
    })
    
    print("\n--- Wait for Replication (3s) ---")
    time.sleep(3)
    
    print("\n--- Performing Transactions ---")
    # Alice withdraws from node 0
    ref1 = str(uuid.uuid4())
    print("Alice (Node 0) withdrawing 500 KES...")
    request(0, "POST", "operation/withdraw", {
        "phone_number": "0700000001", "amount": 500, "client_reference": ref1
    })
    
    # Bob deposits to node 1
    ref2 = str(uuid.uuid4())
    print("Bob (Node 1) depositing 1500 KES...")
    request(1, "POST", "operation/deposit", {
        "phone_number": "0700000002", "amount": 1500, "client_reference": ref2
    })
    
    # Carol transfers to Alice from node 2
    ref3 = str(uuid.uuid4())
    print("Carol (Node 2) transferring 2000 KES to Alice...")
    request(2, "POST", "operation/transfer", {
        "from_account_id": 3, "from_phone_number": "0700000003", 
        "to_phone_number": "0700000001", "amount": 2000, "client_reference": ref3
    })
    
    print("\n--- Wait for Replication (3s) ---")
    time.sleep(3)
    
    print("\n--- Final Balances (checking from Node 0) ---")
    alice = request(0, "POST", "operation/balance", {"phone_number": "0700000001"})
    bob = request(0, "POST", "operation/balance", {"phone_number": "0700000002"})
    carol = request(0, "POST", "operation/balance", {"phone_number": "0700000003"})
    
    print(f"Alice: {alice['data']['balance']} KES")
    print(f"Bob:   {bob['data']['balance']} KES")
    print(f"Carol: {carol['data']['balance']} KES")

if __name__ == "__main__":
    main()
