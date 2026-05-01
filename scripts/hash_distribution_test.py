"""Simple script to test hash ring distribution locally.

Usage: run from repository root with PYTHONPATH=.
"""
import random
from collections import defaultdict

from src.distributed.hashing import ConsistentHash
from src.distributed.utils import normalize_phone


def main():
    servers = {
        'server_1': {'host': 'localhost', 'port': 8001},
        'server_2': {'host': 'localhost', 'port': 8002},
        'server_3': {'host': 'localhost', 'port': 8003},
    }

    ring = ConsistentHash(servers, virtual_nodes=150)
    counts = defaultdict(int)
    N = 10000
    for _ in range(N):
        p = f"07{random.randint(10000000, 99999999)}"
        node = ring.get_node(p)
        counts[node.node_id] += 1

    print("Distribution (N=", N, ")")
    for nid, c in counts.items():
        print(f"{nid}: {c} ({c/N:.2%})")


if __name__ == '__main__':
    main()
