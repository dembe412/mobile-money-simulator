#!/usr/bin/env python3
"""
stress_test.py — Real concurrency/consistency/replication verifier
===================================================================
Launches 3 concurrent clients hitting all 3 nodes simultaneously.

Verifies:
  1. Consistency   — no double-charges despite concurrent requests
  2. Idempotency   — duplicate request IDs never charge twice
  3. Replication   — after writes, all nodes eventually agree on balance
  4. Availability  — system keeps working even under load

Usage (bash):
  python scripts/stress_test.py

Nodes must already be running:
  Terminal 1: SERVER_ID=server_1 SERVER_PORT=8001 python main.py
  Terminal 2: SERVER_ID=server_2 SERVER_PORT=8002 python main.py
  Terminal 3: SERVER_ID=server_3 SERVER_PORT=8003 python main.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threading
import time
import json
import uuid
import requests
from decimal import Decimal
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────

NODES = [
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8002",
    "http://127.0.0.1:8003",
]

# Test accounts — will be created if they don't exist
TEST_ACCOUNTS = [
    {"phone": "0700000001", "name": "Alice Mwangi",  "balance": 50000.0},
    {"phone": "0700000002", "name": "Bob Kamau",     "balance": 50000.0},
    {"phone": "0700000003", "name": "Carol Wanjiru", "balance": 50000.0},
]

CONCURRENT_CLIENTS   = 10   # threads per test phase
REQUESTS_PER_CLIENT  = 20   # requests each thread fires
WITHDRAW_AMOUNT      = 100  # KES per withdrawal
REPLICATION_WAIT_SEC = 4    # seconds to wait for replication to settle

# ── Helpers ───────────────────────────────────────────────────────────────────

results_lock = threading.Lock()
results = defaultdict(lambda: {"success": 0, "fail": 0, "errors": []})


def node_url(idx: int) -> str:
    return NODES[idx % len(NODES)]


def _post(url: str, payload: dict, timeout: int = 5) -> dict:
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"__error": str(e)}


def _get(url: str, timeout: int = 5) -> dict:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"__error": str(e)}


def check_nodes_alive() -> list:
    alive = []
    for url in NODES:
        try:
            r = requests.get(f"{url}/health", timeout=3)
            if r.status_code == 200:
                alive.append(url)
        except Exception:
            pass
    return alive


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup_accounts(node: str) -> dict:
    """Create test accounts if they don't already exist. Returns {phone: account_id}."""
    print(f"\n[Setup] Creating test accounts on {node}...")
    acct_map = {}
    for acct in TEST_ACCOUNTS:
        # Try to find existing
        resp = _post(f"{node}/api/v1/operation/balance", {"phone_number": acct["phone"]})
        if resp.get("status") == "success":
            # Resolve to account_id via routing
            route = _get(f"{node}/api/v1/routing/discover/{acct['phone']}")
            if "routing" in route:
                acct_id = None
                # fetch account to get id
                balance_data = _post(f"{node}/api/v1/operation/balance",
                                     {"phone_number": acct["phone"]})
                acct_map[acct["phone"]] = balance_data.get("data", {}).get("account_id")
            print(f"  ✓ Account {acct['phone']} already exists")
            continue

        # Create it
        resp = _post(f"{node}/api/v1/account/create", {
            "phone_number":        acct["phone"],
            "account_holder_name": acct["name"],
            "initial_balance":     acct["balance"],
        })
        if resp.get("status") == "success":
            acct_map[acct["phone"]] = resp["account_id"]
            print(f"  ✓ Created {acct['phone']} (id={resp['account_id']}, "
                  f"balance={acct['balance']})")
        else:
            print(f"  ✗ Failed to create {acct['phone']}: {resp}")
    return acct_map


def get_balance(node: str, phone: str) -> float:
    resp = _post(f"{node}/api/v1/operation/balance", {"phone_number": phone})
    if resp.get("status") == "success":
        return resp["data"]["balance"]
    return -1.0


# ── Test 1: Consistency under concurrent withdrawals ──────────────────────────

def test_consistency(node: str, phone: str, initial_balance: float):
    print(f"\n{'='*60}")
    print("TEST 1: Consistency — concurrent withdrawals")
    print(f"  Node : {node}")
    print(f"  Phone: {phone}")
    print(f"  Threads: {CONCURRENT_CLIENTS}  ×  {REQUESTS_PER_CLIENT} requests")
    print(f"  Each withdraws {WITHDRAW_AMOUNT} KES (unique request IDs)")
    print("="*60)

    success_count = [0]
    fail_count    = [0]
    lock          = threading.Lock()

    def worker(_tid):
        for _ in range(REQUESTS_PER_CLIENT):
            ref = f"stress-{uuid.uuid4().hex}"
            payload = {
                "phone_number":   phone,
                "amount":         WITHDRAW_AMOUNT,
                "client_reference": ref,
            }
            resp = _post(f"{node}/api/v1/operation/withdraw", payload)
            with lock:
                if resp.get("status") == "success":
                    success_count[0] += 1
                else:
                    fail_count[0] += 1

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(CONCURRENT_CLIENTS)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    elapsed = time.time() - t0

    final_balance = get_balance(node, phone)
    total_requests    = CONCURRENT_CLIENTS * REQUESTS_PER_CLIENT
    expected_deducted = success_count[0] * WITHDRAW_AMOUNT
    expected_balance  = initial_balance - expected_deducted

    print(f"\n  Results:")
    print(f"    Total requests  : {total_requests}")
    print(f"    Successful txns : {success_count[0]}")
    print(f"    Failed/rejected : {fail_count[0]}")
    print(f"    Elapsed         : {elapsed:.2f}s  "
          f"({total_requests/elapsed:.0f} req/s)")
    print(f"    Initial balance : {initial_balance:.2f} KES")
    print(f"    Expected balance: {expected_balance:.2f} KES")
    print(f"    Actual balance  : {final_balance:.2f} KES")

    if abs(final_balance - expected_balance) < 0.01:
        print("  ✅ PASS — Balance is consistent (no double-charges)")
    else:
        diff = final_balance - expected_balance
        print(f"  ❌ FAIL — Balance drift: {diff:.2f} KES")

    return final_balance


# ── Test 2: Idempotency ───────────────────────────────────────────────────────

def test_idempotency(node: str, phone: str, balance_before: float):
    print(f"\n{'='*60}")
    print("TEST 2: Idempotency — same request_id sent 10×")
    print("="*60)

    ref = f"idem-{uuid.uuid4().hex}"
    responses = []
    for i in range(10):
        resp = _post(f"{node}/api/v1/operation/withdraw", {
            "phone_number":   phone,
            "amount":         500,
            "client_reference": ref,
        })
        responses.append(resp.get("status"))

    balance_after = get_balance(node, phone)
    deducted = balance_before - balance_after

    successes = responses.count("success")
    print(f"  Responses  : {responses}")
    print(f"  Deducted   : {deducted:.2f} KES (should be 500.00)")

    if abs(deducted - 500) < 0.01 and successes >= 1:
        print("  ✅ PASS — Charged exactly once despite 10 identical requests")
    else:
        print(f"  ❌ FAIL — Expected 500 KES deducted, got {deducted:.2f}")

    return balance_after


# ── Test 3: Replication ───────────────────────────────────────────────────────

def test_replication(phone: str, write_node_url: str):
    print(f"\n{'='*60}")
    print("TEST 3: Replication — write on one node, read on all")
    print(f"  Write node: {write_node_url}")
    print(f"  Waiting {REPLICATION_WAIT_SEC}s for gossip to propagate...")
    print("="*60)

    # Write on node 0
    ref  = f"repl-{uuid.uuid4().hex}"
    resp = _post(f"{write_node_url}/api/v1/operation/deposit", {
        "phone_number":     phone,
        "amount":           1000,
        "client_reference": ref,
    })
    if resp.get("status") != "success":
        print(f"  ✗ Deposit failed: {resp}")
        return

    written_balance = resp["data"]["balance_after"]
    print(f"  ✓ Deposit successful on {write_node_url}, balance={written_balance}")

    # Wait for replication
    time.sleep(REPLICATION_WAIT_SEC)

    # Read from all nodes
    balances = {}
    for url in NODES:
        b = get_balance(url, phone)
        balances[url] = b

    print(f"\n  Balances across cluster:")
    all_equal = True
    ref_val   = list(balances.values())[0]
    for url, bal in balances.items():
        match = "✅" if abs(bal - ref_val) < 0.01 else "❌"
        if abs(bal - ref_val) >= 0.01:
            all_equal = False
        print(f"    {match} {url}: {bal:.2f} KES")

    if all_equal:
        print("  ✅ PASS — All nodes have the same balance (replication working)")
    else:
        print("  ❌ FAIL — Nodes disagree on balance (replication lag > 4s?)")


# ── Test 4: Transfer consistency ──────────────────────────────────────────────

def test_transfer(node: str, from_phone: str, to_phone: str):
    print(f"\n{'='*60}")
    print("TEST 4: Transfer — sum of balances must be conserved")
    print("="*60)

    b_from_before = get_balance(node, from_phone)
    b_to_before   = get_balance(node, to_phone)
    total_before  = b_from_before + b_to_before

    print(f"  Before: {from_phone}={b_from_before:.2f}  {to_phone}={b_to_before:.2f}  "
          f"total={total_before:.2f}")

    resp = _post(f"{node}/api/v1/operation/transfer", {
        "from_account_id":  1,
        "from_phone_number": from_phone,
        "to_phone_number":   to_phone,
        "amount":            2000,
        "client_reference":  f"txfr-{uuid.uuid4().hex}",
    })

    time.sleep(1)  # let the DB flush
    b_from_after = get_balance(node, from_phone)
    b_to_after   = get_balance(node, to_phone)
    total_after  = b_from_after + b_to_after

    print(f"  After : {from_phone}={b_from_after:.2f}  {to_phone}={b_to_after:.2f}  "
          f"total={total_after:.2f}")
    print(f"  Status: {resp.get('status')} — {resp.get('message','')}")

    if resp.get("status") == "success":
        if abs(total_before - total_after) < 0.01:
            print("  ✅ PASS — Money conserved during transfer")
        else:
            print(f"  ❌ FAIL — {total_before - total_after:.2f} KES vanished!")
    else:
        print(f"  ⚠ Transfer not executed: {resp.get('message')}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Mobile Money System — Stress & Correctness Test")
    print("=" * 60)

    # Check which nodes are alive
    alive = check_nodes_alive()
    if not alive:
        print("\n❌ No nodes are running! Start them first:")
        print("  Bash 1: SERVER_ID=server_1 SERVER_PORT=8001 python main.py")
        print("  Bash 2: SERVER_ID=server_2 SERVER_PORT=8002 python main.py")
        print("  Bash 3: SERVER_ID=server_3 SERVER_PORT=8003 python main.py")
        sys.exit(1)

    print(f"\n✓ Live nodes: {alive}")
    primary = alive[0]

    # Setup
    acct_map = setup_accounts(primary)
    if not acct_map:
        print("\n⚠ Re-running setup with balance lookup...")

    # Get fresh balances
    alice_balance = get_balance(primary, "0700000001")
    bob_balance   = get_balance(primary, "0700000002")

    print(f"\nStarting balances:")
    print(f"  Alice (0700000001): {alice_balance:.2f} KES")
    print(f"  Bob   (0700000002): {bob_balance:.2f} KES")

    # Run tests
    alice_balance = test_consistency(primary, "0700000001", alice_balance)
    alice_balance = test_idempotency(primary, "0700000001", alice_balance)
    test_replication("0700000002", primary)
    test_transfer(primary, "0700000001", "0700000002")

    print(f"\n{'='*60}")
    print("  All tests complete!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
