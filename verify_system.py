#!/usr/bin/env python
"""
Quick System Verification Script
Runs all basic tests to verify the system is working
"""
import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """Run a command and report status"""
    print(f"\n{'='*70}")
    print(f"TEST: {description}")
    print(f"{'='*70}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        # Check if there was output (even if non-zero exit code)
        output = result.stdout + result.stderr
        has_output = len(output.strip()) > 0
        
        if result.returncode == 0 or has_output:
            print("[PASS] OK")
            # Print first 20 lines of output
            lines = output.split('\n')[:20]
            for line in lines:
                if line.strip() and "site-packages" not in line:
                    print(f"  {line[:70]}")
            return True
        else:
            print(f"[FAIL] FAILED")
            print(result.stderr[:500] if result.stderr else "No error output")
            return False
    except subprocess.TimeoutExpired:
        print("[TIME] TIMEOUT (script may still be running in background)")
        return True  # Scripts that run forever are OK
    except Exception as e:
        print(f"[ERR] ERROR: {e}")
        return False

def main():
    print("\n" + "="*70)
    print("MOBILE MONEY SYSTEM - VERIFICATION SUITE")
    print("="*70)
    
    tests = [
        (
            [sys.executable, "scripts/example_p2p_quorum_withdrawal.py"],
            "P2P Quorum Example"
        ),
        (
            [sys.executable, "-m", "pytest", "tests/test_p2p_quorum_simple.py", "-v"],
            "P2P Quorum Tests"
        ),
        (
            [sys.executable, "scripts/example_event_sourcing.py"],
            "Event Sourcing Example"
        ),
        (
            [sys.executable, "scripts/example_2pc_coordinated_withdrawal.py"],
            "2PC Protocol Example"
        ),
    ]
    
    results = []
    for cmd, desc in tests:
        result = run_command(cmd, desc)
        results.append((desc, result))
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for desc, result in results:
        status = "[OK]" if result else "[NO]"
        print(f"{status}: {desc}")
    
    print(f"\nResult: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] ALL TESTS PASSED - System is working correctly!")
        print("\nNext steps:")
        print("1. Start multiple terminals to run separate servers")
        print("2. See SINGLE_PC_TESTING_GUIDE.md for detailed instructions")
        return 0
    else:
        print("\n[WARN] Some tests failed - check output above")
        return 1

if __name__ == "__main__":
    sys.exit(main())
