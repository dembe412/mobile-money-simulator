from __future__ import annotations

import random
import string
from typing import List, Set

from network import Network
from node import Node


def random_request_id(prefix: str) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{suffix}"


def run_simulation(node_count: int = 4, operations: int = 40) -> None:
    print("=" * 80)
    print("EVENT-SOURCED DISTRIBUTED SIMULATION")
    print("=" * 80)
    print("Rules: deposits local-only, withdrawals sync-first and immediately propagated.")
    print()

    network = Network(min_delay_ms=20, max_delay_ms=160)
    nodes: List[Node] = [
        Node(node_id=f"node_{i+1}", network=network, initial_balance=1000.0)
        for i in range(node_count)
    ]

    for i in range(1, operations + 1):
        node = random.choice(nodes)
        op = random.choices(["deposit", "withdraw"], weights=[0.65, 0.35], k=1)[0]

        if op == "deposit":
            amount = round(random.uniform(10, 300), 2)
            request_id = random_request_id("dep")
            print(f"\n[OP {i:02d}] {node.node_id} DEPOSIT {amount:.2f}")
            ok = node.deposit(amount=amount, request_id=request_id)
            if not ok:
                print(f"[OP {i:02d}] deposit rejected (idempotency/validation)")
        else:
            amount = round(random.uniform(20, 500), 2)
            request_id = random_request_id("wd")
            print(f"\n[OP {i:02d}] {node.node_id} WITHDRAW {amount:.2f}")
            ok = node.withdraw(withdraw_amount=amount, request_id=request_id)
            if not ok:
                print(f"[OP {i:02d}] withdrawal rejected")

    print("\n" + "-" * 80)
    print("FINAL GLOBAL SYNC")
    print("-" * 80)
    for node in nodes:
        node.sync_all()
        node.recompute_from_checkpoint()

    print("\n" + "-" * 80)
    print("VALIDATION")
    print("-" * 80)
    balances = [n.checkpoint.balance for n in nodes]
    converged = all(abs(b - balances[0]) < 1e-9 for b in balances)
    non_negative = all(b >= 0 for b in balances)

    # Check duplicate IDs per node.
    any_node_has_dups = False
    for node in nodes:
        ids = [e.event_id for e in node.event_log.all_events()]
        node_unique = len(ids) == len(set(ids))
        if not node_unique:
            any_node_has_dups = True
            print(f"[FAIL] {node.node_id} has duplicate event IDs")

    for node in nodes:
        print(
            f"{node.node_id}: balance={node.checkpoint.balance:.2f}, "
            f"last_event_id={node.checkpoint.last_event_id}, "
            f"events={node.event_log.event_count()}"
        )

    print()
    print(f"Converged balances: {'PASS' if converged else 'FAIL'}")
    print(f"No negative balances: {'PASS' if non_negative else 'FAIL'}")
    print(f"No duplicate event IDs: {'PASS' if not any_node_has_dups else 'FAIL'}")
    print(
        "No double-spend behavior: "
        f"{'PASS' if (converged and non_negative and not any_node_has_dups) else 'CHECK LOGS'}"
    )


if __name__ == "__main__":
    random.seed(42)
    run_simulation(node_count=4, operations=35)
