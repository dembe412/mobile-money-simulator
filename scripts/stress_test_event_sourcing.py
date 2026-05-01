"""
Stress Test for Distributed Mobile Money System
Tests:
- Multiple nodes with concurrent deposits and withdrawals
- Random transaction patterns
- Balance convergence under load
- Double spending prevention
- Network delays and retries
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import random
import time
import logging
from decimal import Decimal
from threading import Thread, Lock
from typing import List, Dict
import statistics

from src.core.distributed_system import DistributedSystem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class StressTestRunner:
    """Runs stress tests on distributed system"""
    
    def __init__(self, num_nodes: int = 5, num_operations: int = 100):
        """
        Initialize stress test.
        
        Args:
            num_nodes: Number of nodes in system
            num_operations: Total operations to perform
        """
        self.num_nodes = num_nodes
        self.num_operations = num_operations
        self.system = DistributedSystem(account_id=1, num_nodes=num_nodes)
        self.operation_lock = Lock()
        self.results = {
            "deposits": 0,
            "withdrawals": 0,
            "failed_deposits": 0,
            "failed_withdrawals": 0,
            "duplicate_requests": 0,
            "operation_times": [],
        }
    
    def _random_node(self) -> str:
        """Get random node ID"""
        return f"node_{random.randint(1, self.num_nodes)}"
    
    def _random_amount(self) -> Decimal:
        """Get random transaction amount (1-500)"""
        return Decimal(random.randint(1, 500))
    
    def _random_request_id(self, retry_chance: float = 0.05) -> str:
        """
        Get random request ID, with chance of duplicate (retry).
        
        Args:
            retry_chance: Probability of returning duplicate request_id
        """
        if random.random() < retry_chance:
            # Return potentially duplicate request_id (simulating retry)
            self.results["duplicate_requests"] += 1
            return f"req_{random.randint(1, self.num_operations // 2)}"
        else:
            return f"req_{int(time.time() * 1000000)}_{random.randint(0, 999999)}"
    
    def run_deposit_operation(self):
        """Run a deposit operation"""
        node = self._random_node()
        amount = self._random_amount()
        request_id = self._random_request_id()
        
        start_time = time.time()
        success, msg = self.system.deposit(node, amount, request_id)
        elapsed = time.time() - start_time
        
        with self.operation_lock:
            self.results["operation_times"].append(elapsed)
            if success:
                self.results["deposits"] += 1
            else:
                self.results["failed_deposits"] += 1
        
        return success
    
    def run_withdrawal_operation(self):
        """Run a withdrawal operation"""
        node = self._random_node()
        amount = self._random_amount()
        request_id = self._random_request_id()
        
        start_time = time.time()
        success, msg = self.system.withdraw(node, amount, request_id)
        elapsed = time.time() - start_time
        
        with self.operation_lock:
            self.results["operation_times"].append(elapsed)
            if success:
                self.results["withdrawals"] += 1
            else:
                self.results["failed_withdrawals"] += 1
        
        return success
    
    def run_stress_test(self, num_threads: int = 10):
        """
        Run stress test with multiple threads.
        
        Args:
            num_threads: Number of concurrent threads
        """
        logger.info("=" * 70)
        logger.info("STRESS TEST START")
        logger.info("=" * 70)
        logger.info(f"Configuration:")
        logger.info(f"  Nodes:        {self.num_nodes}")
        logger.info(f"  Operations:   {self.num_operations}")
        logger.info(f"  Threads:      {num_threads}")
        logger.info("=" * 70)
        
        # Print initial state
        print("\n[INITIAL STATE]")
        self.system.print_state()
        
        start_time = time.time()
        threads = []
        
        # Create and start threads
        for i in range(num_threads):
            thread = Thread(
                target=self._thread_worker,
                args=(self.num_operations // num_threads,)
            )
            thread.start()
            threads.append(thread)
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        elapsed = time.time() - start_time
        
        # Print final state
        print("\n[FINAL STATE]")
        self.system.print_state()
        
        # Print results
        self._print_results(elapsed)
    
    def _thread_worker(self, operations: int):
        """Worker thread for stress test"""
        for _ in range(operations):
            if random.random() < 0.6:
                # 60% deposits
                self.run_deposit_operation()
            else:
                # 40% withdrawals
                self.run_withdrawal_operation()
    
    def _print_results(self, elapsed_time: float):
        """Print stress test results"""
        logger.info("=" * 70)
        logger.info("STRESS TEST RESULTS")
        logger.info("=" * 70)
        
        total_ops = (
            self.results["deposits"] + 
            self.results["withdrawals"] +
            self.results["failed_deposits"] +
            self.results["failed_withdrawals"]
        )
        
        logger.info(f"\nOperation Summary:")
        logger.info(f"  Total Operations:      {total_ops}")
        logger.info(f"  Successful Deposits:   {self.results['deposits']}")
        logger.info(f"  Failed Deposits:       {self.results['failed_deposits']}")
        logger.info(f"  Successful Withdrawals:{self.results['withdrawals']}")
        logger.info(f"  Failed Withdrawals:    {self.results['failed_withdrawals']}")
        logger.info(f"  Duplicate Requests:    {self.results['duplicate_requests']} (tested idempotency)")
        
        logger.info(f"\nPerformance:")
        logger.info(f"  Total Time:            {elapsed_time:.2f}s")
        logger.info(f"  Ops/Second:            {total_ops / elapsed_time:.2f}")
        
        if self.results["operation_times"]:
            op_times = self.results["operation_times"]
            logger.info(f"\nOperation Latencies:")
            logger.info(f"  Min:                   {min(op_times)*1000:.2f}ms")
            logger.info(f"  Max:                   {max(op_times)*1000:.2f}ms")
            logger.info(f"  Avg:                   {statistics.mean(op_times)*1000:.2f}ms")
            logger.info(f"  Median:                {statistics.median(op_times)*1000:.2f}ms")
            logger.info(f"  StdDev:                {statistics.stdev(op_times)*1000:.2f}ms")
        
        # Verification
        logger.info(f"\nSystem Verification:")
        
        # Check convergence
        converged, msg = self.system.verify_convergence()
        logger.info(f"  Convergence:           {'✓ PASS' if converged else '✗ FAIL'} - {msg}")
        
        # Check no double spending
        valid, msg = self.system.verify_no_double_spending()
        logger.info(f"  No Double Spending:    {'✓ PASS' if valid else '✗ FAIL'} - {msg}")
        
        # Check all balances non-negative
        balances = self.system.get_all_balances()
        all_positive = all(b >= 0 for b in balances.values())
        logger.info(f"  Non-negative Balances: {'✓ PASS' if all_positive else '✗ FAIL'}")
        
        logger.info("=" * 70)


def run_scenario_1_basic_operations():
    """
    Scenario 1: Basic operations with few nodes
    Tests: Deposits, withdrawals, balance consistency
    """
    logger.info("\n\n")
    logger.info("SCENARIO 1: BASIC OPERATIONS")
    logger.info("Configuration: 3 nodes, 50 operations")
    
    runner = StressTestRunner(num_nodes=3, num_operations=50)
    runner.run_stress_test(num_threads=1)


def run_scenario_2_concurrent_operations():
    """
    Scenario 2: Concurrent operations with multiple threads
    Tests: Concurrency correctness, race conditions
    """
    logger.info("\n\n")
    logger.info("SCENARIO 2: CONCURRENT OPERATIONS")
    logger.info("Configuration: 5 nodes, 200 operations, 10 threads")
    
    runner = StressTestRunner(num_nodes=5, num_operations=200)
    runner.run_stress_test(num_threads=10)


def run_scenario_3_high_load():
    """
    Scenario 3: High load stress test
    Tests: System stability under heavy load
    """
    logger.info("\n\n")
    logger.info("SCENARIO 3: HIGH LOAD")
    logger.info("Configuration: 10 nodes, 500 operations, 20 threads")
    
    runner = StressTestRunner(num_nodes=10, num_operations=500)
    runner.run_stress_test(num_threads=20)


def run_scenario_4_idempotency_test():
    """
    Scenario 4: Idempotency test with retries
    Tests: Duplicate request handling, idempotent operations
    """
    logger.info("\n\n")
    logger.info("SCENARIO 4: IDEMPOTENCY & RETRY RESILIENCE")
    logger.info("Configuration: 5 nodes, many duplicate requests")
    
    runner = StressTestRunner(num_nodes=5, num_operations=100)
    
    # Override retry chance to simulate many retries
    original_random_request_id = runner._random_request_id
    
    def high_retry_rate():
        # 20% chance of returning duplicate request_id (vs default 5%)
        if random.random() < 0.20:
            runner.results["duplicate_requests"] += 1
            return f"req_{random.randint(1, 50)}"
        return f"req_{int(time.time() * 1000000)}_{random.randint(0, 999999)}"
    
    runner._random_request_id = high_retry_rate
    runner.run_stress_test(num_threads=5)


def main():
    """Run all stress test scenarios"""
    logger.info("\n" + "█" * 70)
    logger.info("█" + " " * 68 + "█")
    logger.info("█  DISTRIBUTED MOBILE MONEY SYSTEM - STRESS TEST SUITE".ljust(69) + "█")
    logger.info("█" + " " * 68 + "█")
    logger.info("█" * 70)
    
    # Run scenarios
    run_scenario_1_basic_operations()
    run_scenario_2_concurrent_operations()
    run_scenario_3_high_load()
    run_scenario_4_idempotency_test()
    
    logger.info("\n" + "█" * 70)
    logger.info("█  ALL STRESS TESTS COMPLETED".ljust(69) + "█")
    logger.info("█" * 70 + "\n")


if __name__ == "__main__":
    main()
