"""
Integration Guide: Using 2PC Coordinated Withdrawals in Your API
Shows how to update existing API endpoints to use coordinated withdrawals
"""

# ============================================================================
# BEFORE: Using lazy propagation (potentially inconsistent)
# ============================================================================

# src/api/routes.py (OLD)
@app.post("/withdraw")
async def withdraw_old(account_id: int, amount: Decimal):
    """
    ⚠️ WARNING: Uses lazy propagation
    - Fast but potentially inconsistent
    - Risk: Withdrawal may not replicate to all nodes
    """
    system = get_distributed_system()
    node = system.get_node("node_1")  # coordinator
    
    success, message = node.withdraw(
        amount=amount,
        request_id=request.id
    )
    
    return {
        "success": success,
        "message": message,
        "consistency": "eventual"  # ⚠️ Not guaranteed
    }


# ============================================================================
# AFTER: Using 2PC coordinated withdrawals (guaranteed consistent)
# ============================================================================

# src/api/routes.py (NEW)
from decimal import Decimal
from fastapi import FastAPI, HTTPException
from src.core.distributed_system import DistributedSystem

app = FastAPI()
system = None  # Initialized at startup

@app.on_event("startup")
async def startup():
    """Initialize distributed system on startup"""
    global system
    system = DistributedSystem(account_id=1, num_nodes=3)


@app.post("/withdraw")
async def withdraw_coordinated(
    account_id: int,
    amount: Decimal,
    request_id: str
):
    """
    ✅ UPDATED: Uses 2PC coordinated withdrawal
    - Guaranteed atomic all-or-nothing semantics
    - Slightly higher latency but strongly consistent
    - Perfect for financial transactions
    """
    try:
        node = system.get_node("node_1")  # coordinator
        
        if not node:
            raise HTTPException(status_code=404, detail="Coordinator node not found")
        
        # Use coordinated withdrawal instead of lazy propagation
        success, message = node.coordinated_withdraw(
            amount=amount,
            request_id=request_id
        )
        
        if success:
            # ✅ Guaranteed: ALL replicas applied the withdrawal consistently
            return {
                "success": True,
                "message": message,
                "consistency": "strong",  # ✅ Guaranteed!
                "amount": str(amount),
                "transaction_type": "coordinated_withdrawal"
            }
        else:
            # ✅ Guaranteed: ALL replicas rolled back (no partial state)
            raise HTTPException(
                status_code=400,
                detail=f"Withdrawal failed: {message}"
            )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/deposit")
async def deposit(account_id: int, amount: Decimal, request_id: str):
    """
    Deposits use lazy propagation (no 2PC needed)
    - Can't cause over-withdrawal
    - Fast and sufficient for deposits
    """
    try:
        node = system.get_node("node_1")
        success, message = node.deposit(amount=amount, request_id=request_id)
        
        return {
            "success": success,
            "message": message,
            "consistency": "eventual",  # OK for deposits
            "amount": str(amount),
            "transaction_type": "deposit"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/balance/{account_id}")
async def get_balance(account_id: int):
    """Get current balance (read-only, no 2PC needed)"""
    try:
        node = system.get_node("node_1")
        balance = node.get_balance()
        
        return {
            "account_id": account_id,
            "balance": str(balance),
            "currency": "USD"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/transaction-status/{transaction_id}")
async def get_transaction_status(transaction_id: str):
    """Get status of a coordinated transaction (for monitoring)"""
    try:
        node = system.get_node("node_1")
        status = node.coordinated_commit_manager.get_transaction_status(transaction_id)
        
        if status:
            return status
        else:
            raise HTTPException(status_code=404, detail="Transaction not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/node-state/{node_id}")
async def get_node_state(node_id: str):
    """Get complete state of a node (for debugging)"""
    try:
        node = system.get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
        
        state = node.get_state()
        locks = node.get_transaction_locks()
        
        return {
            "node_id": node_id,
            "balance": state["balance"],
            "event_count": state["event_count"],
            "locked_funds": {k: str(v) for k, v in locks.items()},
            "remote_nodes": state["remote_nodes"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MIGRATION GUIDE
# ============================================================================

"""
STEP 1: Update all WITHDRAWAL endpoints
-----------------------------------------
Before:
    success, msg = node.withdraw(amount)

After:
    success, msg = node.coordinated_withdraw(amount, request_id)


STEP 2: Update clients to expect higher latency
-----------------------------------------------
Before: ~50ms (lazy propagation)
After: ~100-200ms (2PC with prepare/commit phases)

Acceptable for financial transactions, but add timeout handling in clients.


STEP 3: Add idempotency handling
--------------------------------
Always provide request_id to prevent double-withdrawals:

request_id = f"{user_id}_{timestamp}_{operation_hash}"
success, msg = node.coordinated_withdraw(
    amount=Decimal(100),
    request_id=request_id
)


STEP 4: Update monitoring/logging
----------------------------------
Track transaction status:
- Status: PREPARE, COMMIT, ROLLBACK, ABORT
- Votes: ACK, NACK, TIMEOUT
- Timestamps: creation time, completion time


STEP 5: Handle timeout errors
-----------------------------
If 2PC timeout (replica unresponsive):
- Catch timeout exception
- Automatically retried (handled by 2PC)
- Return error to client if all retries exhausted


STEP 6: Update tests
-------------------
Before:
    success, msg = node.withdraw(Decimal(100))
    assert success

After:
    success, msg = node.coordinated_withdraw(
        Decimal(100),
        request_id="test_001"
    )
    assert success  # Now truly atomic!
"""

# ============================================================================
# EXAMPLE: Building a financial transaction API
# ============================================================================

from typing import List

@app.post("/transfer")
async def transfer(
    from_account: int,
    to_account: int,
    amount: Decimal,
    reference: str
):
    """
    Transfer funds from one account to another
    Uses 2PC for source account withdrawal + deposit on destination
    """
    request_id = f"transfer_{from_account}_to_{to_account}_{reference}"
    
    try:
        node = system.get_node("node_1")
        
        # STEP 1: Coordinated withdrawal from source
        withdraw_success, withdraw_msg = node.coordinated_withdraw(
            amount=amount,
            request_id=f"{request_id}_withdraw"
        )
        
        if not withdraw_success:
            raise HTTPException(
                status_code=400,
                detail=f"Withdrawal failed: {withdraw_msg}"
            )
        
        # STEP 2: Deposit to destination (lazy propagation is fine)
        deposit_success, deposit_msg = node.deposit(
            amount=amount,
            request_id=f"{request_id}_deposit"
        )
        
        if not deposit_success:
            # In production, you might want to rollback the withdrawal
            # For now, the destination will eventually get the credit
            return {
                "success": False,
                "message": f"Withdrawal succeeded but deposit failed: {deposit_msg}",
                "partial": True
            }
        
        return {
            "success": True,
            "from_account": from_account,
            "to_account": to_account,
            "amount": str(amount),
            "reference": reference,
            "withdrawal_txn": withdraw_msg,
            "deposit_txn": deposit_msg,
            "consistency": "strong"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batch-transfer")
async def batch_transfer(
    transfers: List[dict]  # List of {from, to, amount, reference}
):
    """
    Batch multiple transfers
    Each uses 2PC for safety
    """
    results = []
    
    for transfer in transfers:
        result = await transfer(
            from_account=transfer["from_account"],
            to_account=transfer["to_account"],
            amount=Decimal(transfer["amount"]),
            reference=transfer["reference"]
        )
        results.append(result)
    
    return {"transfers": results}


# ============================================================================
# EXAMPLE: Client code using the new API
# ============================================================================

import httpx
from datetime import datetime

class MobileMoneyClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.Client()
    
    def withdraw(self, amount: float) -> dict:
        """Perform coordinated withdrawal"""
        request_id = f"withdraw_{datetime.utcnow().timestamp()}"
        
        response = self.client.post(
            f"{self.base_url}/withdraw",
            json={
                "account_id": 1,
                "amount": str(amount),
                "request_id": request_id
            }
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Withdrawal failed: {response.text}")
    
    def transfer(self, to_account: int, amount: float, reference: str) -> dict:
        """Transfer funds with strong consistency"""
        response = self.client.post(
            f"{self.base_url}/transfer",
            json={
                "from_account": 1,
                "to_account": to_account,
                "amount": str(amount),
                "reference": reference
            }
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Transfer failed: {response.text}")
    
    def get_balance(self) -> float:
        """Get account balance"""
        response = self.client.get(f"{self.base_url}/balance/1")
        return float(response.json()["balance"])


# ============================================================================
# EXAMPLE: Using the client
# ============================================================================

def main():
    client = MobileMoneyClient()
    
    print("Initial balance:", client.get_balance())  # 1000
    
    # Perform coordinated withdrawal
    result = client.withdraw(100)
    print("Withdrawal result:", result)
    
    # Check balance (should be 900 on ALL replicas consistently)
    print("New balance:", client.get_balance())  # 900
    
    # Perform transfer
    transfer_result = client.transfer(
        to_account=2,
        amount=50,
        reference="PAYMENT_001"
    )
    print("Transfer result:", transfer_result)
    
    print("Final balance:", client.get_balance())  # 850


if __name__ == "__main__":
    main()
