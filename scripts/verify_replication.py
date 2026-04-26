#!/usr/bin/env python3
"""
verify_replication.py — Cross-node balance consistency checker
==============================================================
Directly reads the SQLite database files for each server and
compares balances, transaction counts, and event logs.

No HTTP calls — reads raw SQLite files.

Usage:
  python scripts/verify_replication.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"

SERVERS = ["server_1", "server_2", "server_3"]


def read_db(server_id: str) -> dict:
    db_path = DATA_DIR / f"{server_id}.db"
    if not db_path.exists():
        return {"error": f"DB not found: {db_path}"}

    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.row_factory = sqlite3.Row

    try:
        # Accounts
        accounts = conn.execute(
            "SELECT phone_number, balance, account_status, version FROM accounts ORDER BY phone_number"
        ).fetchall()

        # Transactions
        txn_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        # Events
        event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        replicated  = conn.execute(
            "SELECT COUNT(*) FROM events WHERE is_replicated=1"
        ).fetchone()[0]

        return {
            "server_id":    server_id,
            "db_path":      str(db_path),
            "accounts":     [dict(r) for r in accounts],
            "txn_count":    txn_count,
            "event_count":  event_count,
            "replicated":   replicated,
        }
    finally:
        conn.close()


def main():
    print("=" * 60)
    print("  Replication Verification — Direct SQLite Comparison")
    print(f"  Data dir: {DATA_DIR}")
    print("=" * 60)

    all_data = {}
    for server_id in SERVERS:
        data = read_db(server_id)
        all_data[server_id] = data
        if "error" in data:
            print(f"\n⚠  {server_id}: {data['error']}")
        else:
            print(f"\n✓  {server_id}  ({data['txn_count']} txns, "
                  f"{data['event_count']} events, "
                  f"{data['replicated']} replicated)")

    # Compare balances across nodes
    print(f"\n{'─'*60}")
    print("  Balance Comparison Across Nodes")
    print(f"{'─'*60}")

    # Collect all phones seen
    all_phones = set()
    for data in all_data.values():
        if "accounts" in data:
            for acct in data["accounts"]:
                all_phones.add(acct["phone_number"])

    if not all_phones:
        print("  No accounts found in any database yet.")
        return

    header = f"{'Phone':<15}" + "".join(f"{s:<14}" for s in SERVERS) + "  Consistent?"
    print(f"  {header}")
    print(f"  {'─'*len(header)}")

    all_consistent = True
    for phone in sorted(all_phones):
        balances = {}
        for sid, data in all_data.items():
            if "accounts" in data:
                match = next((a for a in data["accounts"]
                              if a["phone_number"] == phone), None)
                balances[sid] = match["balance"] if match else "N/A"
            else:
                balances[sid] = "ERR"

        vals  = list(balances.values())
        try:
            nums  = [float(v) for v in vals if v not in ("N/A", "ERR")]
            ok    = len(nums) == len(vals) and all(abs(n - nums[0]) < 0.01 for n in nums)
        except Exception:
            ok = False

        if not ok:
            all_consistent = False

        icon = "✅" if ok else "❌"
        row  = f"{phone:<15}" + "".join(f"{str(balances[s]):<14}" for s in SERVERS)
        print(f"  {icon} {row}")

    print()
    if all_consistent:
        print("  ✅ PASS — All nodes agree on all balances")
    else:
        print("  ❌ FAIL — Nodes disagree (replication may still be in progress)")
        print("           Try again in a few seconds — gossip interval is 2s")

    # Event replication summary
    print(f"\n{'─'*60}")
    print("  Event Log Summary")
    print(f"{'─'*60}")
    for sid, data in all_data.items():
        if "error" not in data:
            pct = (data["replicated"] / data["event_count"] * 100
                   if data["event_count"] > 0 else 0)
            print(f"  {sid}: {data['event_count']} events, "
                  f"{data['replicated']} replicated ({pct:.0f}%)")


if __name__ == "__main__":
    main()
