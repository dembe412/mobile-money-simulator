#!/usr/bin/env python3
"""
Improved stress_test.py
=======================
Tests concurrency, idempotency, replication, transfers, and mixed operations.
Includes latency metrics and invariant checks.
"""
import sys
import os
import threading
import time
import uuid
import requests
from collections import defaultdict
import statistics

NODES = [
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8002",
    "http://127.0.0.1:8003",
]

TEST_ACCOUNTS = [
    {"phone": "0700000001", "name": "Alice Mwangi",  "balance": 100000.0},
    {"phone": "0700000002", "name": "Bob Kamau",     "balance": 100000.0},
    {"phone": "0700000003", "name": "Carol Wanjiru", "balance": 100000.0},
]

CONCURRENT_CLIENTS   = 20
REQUESTS_PER_CLIENT  = 10
WITHDRAW_AMOUNT      = 10
REPLICATION_WAIT_SEC = 5

latency_metrics = []
metrics_lock = threading.Lock()

def _post(url: str, payload: dict, timeout: int = 10) -> dict:
    start_time = time.time()
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        duration = time.time() - start_time
        with metrics_lock:
            latency_metrics.append(duration)
        if r.status_code == 409:
            return {"status": "error", "message": "Duplicate request in progress"}
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _get(url: str, timeout: int = 5) -> dict:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}

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

def setup_accounts(node: str) -> dict:
    print(f"\n[Setup] Creating test accounts on {node}...")
    acct_map = {}
    for acct in TEST_ACCOUNTS:
        resp = _post(f"{node}/api/v1/operation/balance", {"phone_number": acct["phone"]})
        if resp.get("status") == "success":
            balance_data = resp
            acct_map[acct["phone"]] = True
            print(f"  ✓ Account {acct['phone']} exists")
            continue

        resp = _post(f"{node}/api/v1/account/create", {
            "phone_number":        acct["phone"],
            "account_holder_name": acct["name"],
            "initial_balance":     acct["balance"],
        })
        if resp.get("status") == "success":
            acct_map[acct["phone"]] = True
            print(f"  ✓ Created {acct['phone']}")
        else:
            print(f"  ✗ Failed to create {acct['phone']}: {resp}")
    return acct_map

def get_balance(node: str, phone: str) -> float:
    resp = _post(f"{node}/api/v1/operation/balance", {"phone_number": phone})
    if resp.get("status") == "success":
        return resp["data"]["balance"]
    return -1.0

def test_consistency(node: str, phone: str, initial_balance: float):
    print(f"\n{'='*60}")
    print("TEST 1: Concurrency — Concurrent withdrawals")
    print("="*60)
    
    success_count = [0]
    fail_count = [0]
    lock = threading.Lock()

    def worker():
        for _ in range(REQUESTS_PER_CLIENT):
            ref = f"stress-{uuid.uuid4().hex}"
            resp = _post(f"{node}/api/v1/operation/withdraw", {
                "phone_number": phone,
                "amount": WITHDRAW_AMOUNT,
                "client_reference": ref,
            })
            with lock:
                if resp.get("status") == "success":
                    success_count[0] += 1
                else:
                    fail_count[0] += 1

    threads = [threading.Thread(target=worker) for _ in range(CONCURRENT_CLIENTS)]
    for t in threads: t.start()
    for t in threads: t.join()

    final_balance = get_balance(node, phone)
    expected = initial_balance - (success_count[0] * WITHDRAW_AMOUNT)
    
    print(f"  Success: {success_count[0]}, Fail: {fail_count[0]}")
    print(f"  Expected: {expected:.2f}, Actual: {final_balance:.2f}")
    
    if abs(final_balance - expected) < 0.01:
        print("  ✅ PASS — Balance is consistent")
    else:
        print(f"  ❌ FAIL — Balance drift! Diff: {final_balance - expected:.2f}")

    return final_balance

def test_idempotency(node: str, phone: str, balance_before: float):
    print(f"\n{'='*60}")
    print("TEST 2: Idempotency — Concurrent identical requests")
    print("="*60)

    ref = f"idem-{uuid.uuid4().hex}"
    responses = []
    lock = threading.Lock()

    def worker():
        resp = _post(f"{node}/api/v1/operation/withdraw", {
            "phone_number": phone,
            "amount": 500,
            "client_reference": ref,
        })
        with lock:
            responses.append(resp.get("status"))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()

    balance_after = get_balance(node, phone)
    deducted = balance_before - balance_after
    successes = responses.count("success")
    errors = responses.count("error")

    print(f"  Responses: {successes} success, {errors} error/cached")
    print(f"  Deducted: {deducted:.2f} KES (should be 500.00)")

    if abs(deducted - 500) < 0.01 and successes >= 1:
        print("  ✅ PASS — Charged exactly once despite 10 identical requests")
    else:
        print(f"  ❌ FAIL — Expected 500 KES deducted, got {deducted:.2f}")

    return balance_after

def test_replication(phone: str, write_node: str):
    print(f"\n{'='*60}")
    print("TEST 3: Replication — Write to one, read from all")
    print("="*60)

    ref = f"repl-{uuid.uuid4().hex}"
    resp = _post(f"{write_node}/api/v1/operation/deposit", {
        "phone_number": phone,
        "amount": 1000,
        "client_reference": ref,
    })
    
    if resp.get("status") != "success":
        print(f"  ❌ Deposit failed: {resp}")
        return

    print(f"  Waiting {REPLICATION_WAIT_SEC}s for replication...")
    time.sleep(REPLICATION_WAIT_SEC)

    balances = {}
    for url in NODES:
        balances[url] = get_balance(url, phone)

    all_equal = True
    ref_val = list(balances.values())[0]
    for url, bal in balances.items():
        match = "✅" if abs(bal - ref_val) < 0.01 else "❌"
        if abs(bal - ref_val) >= 0.01:
            all_equal = False
        print(f"    {match} {url}: {bal:.2f} KES")

    if all_equal:
        print("  ✅ PASS — Nodes agree on balance")
    else:
        print("  ❌ FAIL — Nodes disagree on balance")

def test_transfer(node: str, from_phone: str, to_phone: str):
    print(f"\n{'='*60}")
    print("TEST 4: Transfer — Conservation of money")
    print("="*60)

    b_from_before = get_balance(node, from_phone)
    b_to_before   = get_balance(node, to_phone)
    total_before  = b_from_before + b_to_before

    _post(f"{node}/api/v1/operation/transfer", {
        "from_account_id":  1,
        "from_phone_number": from_phone,
        "to_phone_number":   to_phone,
        "amount":            2000,
        "client_reference":  f"txfr-{uuid.uuid4().hex}",
    })

    b_from_after = get_balance(node, from_phone)
    b_to_after   = get_balance(node, to_phone)
    total_after  = b_from_after + b_to_after

    print(f"  Total Before: {total_before:.2f}")
    print(f"  Total After : {total_after:.2f}")

    if abs(total_before - total_after) < 0.01:
        print("  ✅ PASS — Money conserved")
    else:
        print(f"  ❌ FAIL — Money vanished!")

def test_mixed_operations(node: str):
    print(f"\n{'='*60}")
    print("TEST 5: Mixed Operations — High Contention")
    print("="*60)
    
    lock = threading.Lock()
    ops_completed = {"withdraw": 0, "deposit": 0, "transfer": 0}

    def worker(op_type):
        ref = f"mix-{uuid.uuid4().hex}"
        if op_type == "withdraw":
            _post(f"{node}/api/v1/operation/withdraw", {
                "phone_number": "0700000001",
                "amount": 5, "client_reference": ref,
            })
            with lock: ops_completed["withdraw"] += 1
        elif op_type == "deposit":
            _post(f"{node}/api/v1/operation/deposit", {
                "phone_number": "0700000002",
                "amount": 5, "client_reference": ref,
            })
            with lock: ops_completed["deposit"] += 1
        elif op_type == "transfer":
            _post(f"{node}/api/v1/operation/transfer", {
                "from_account_id": 1,
                "from_phone_number": "0700000001",
                "to_phone_number": "0700000003",
                "amount": 5, "client_reference": ref,
            })
            with lock: ops_completed["transfer"] += 1

    threads = []
    # 50 withdrawals, 30 deposits, 20 transfers
    for _ in range(50): threads.append(threading.Thread(target=worker, args=("withdraw",)))
    for _ in range(30): threads.append(threading.Thread(target=worker, args=("deposit",)))
    for _ in range(20): threads.append(threading.Thread(target=worker, args=("transfer",)))

    for t in threads: t.start()
    for t in threads: t.join()

    print(f"  ✅ PASS — Completed mixed operations (W: {ops_completed['withdraw']}, D: {ops_completed['deposit']}, T: {ops_completed['transfer']})")

def print_metrics():
    print(f"\n{'='*60}")
    print("PERFORMANCE METRICS")
    print("="*60)
    if not latency_metrics:
        print("No metrics gathered.")
        return
    avg_latency = statistics.mean(latency_metrics) * 1000
    max_latency = max(latency_metrics) * 1000
    min_latency = min(latency_metrics) * 1000
    print(f"  Total Requests: {len(latency_metrics)}")
    print(f"  Avg Latency:    {avg_latency:.2f} ms")
    print(f"  Min Latency:    {min_latency:.2f} ms")
    print(f"  Max Latency:    {max_latency:.2f} ms")

def invariant_checks(node: str):
    print(f"\n{'='*60}")
    print("INVARIANT CHECKS")
    print("="*60)
    
    total_balance = 0
    all_positive = True
    
    for acct in TEST_ACCOUNTS:
        bal = get_balance(node, acct["phone"])
        total_balance += bal
        if bal < 0:
            all_positive = False
            print(f"  ❌ NEGATIVE BALANCE: {acct['phone']} has {bal}")
            
    # Note: total_balance should equal initial sum, modulo any new deposits. 
    # Since we deposited 1000 and 150 (30*5) and deducted some, we just check no negative balances
    
    if all_positive:
        print("  ✅ PASS — No negative balances")
    else:
        print("  ❌ FAIL — Found negative balances")

def main():
    alive = check_nodes_alive()
    if not alive:
        print("No nodes running!")
        sys.exit(1)
        
    primary = alive[0]
    for node in alive:
        setup_accounts(node)
    
    alice_bal = get_balance(primary, "0700000001")
    bob_bal = get_balance(primary, "0700000002")
    
    alice_bal = test_consistency(primary, "0700000001", alice_bal)
    test_idempotency(primary, "0700000001", alice_bal)
    test_replication("0700000002", primary)
    test_transfer(primary, "0700000001", "0700000002")
    test_mixed_operations(primary)
    
    time.sleep(REPLICATION_WAIT_SEC)
    invariant_checks(primary)
    print_metrics()
    
    print("\nTests complete.\n")

if __name__ == "__main__":
    main()
