"""
Core account operations: Withdraw, Deposit, Check Balance
Implements pessimistic locking for concurrency control
"""
from sqlalchemy.orm import Session
from sqlalchemy import select
from decimal import Decimal
from datetime import datetime, timedelta
import logging
from typing import Tuple, Dict, Any

from src.models import Account, Transaction, AccountLock, Request
from config.settings import operation_config, server_config

logger = logging.getLogger(__name__)


class OperationError(Exception):
    """Custom exception for operation failures"""
    pass


class InsufficientBalanceError(OperationError):
    """Raised when account has insufficient balance"""
    pass


class LockAcquisitionError(OperationError):
    """Raised when lock cannot be acquired"""
    pass


class AccountLockedError(OperationError):
    """Raised when account is locked by another operation"""
    pass


class AccountOperations:
    """Core business logic for account operations"""
    
    @staticmethod
    def resolve_account(
        db: Session,
        account_id: int = None,
        phone_number: str = None
    ) -> Tuple[bool, str, Account]:
        """
        Resolve account by ID or phone number
        
        Args:
            db: Database session
            account_id: Account ID (optional)
            phone_number: Phone number (optional)
            
        Returns:
            (success: bool, message: str, account: Account or None)
        """
        try:
            account = None
            
            # Try phone_number lookup first (preferred)
            if phone_number:
                account = db.query(Account).filter(
                    Account.phone_number == phone_number
                ).first()
                if account:
                    return True, "Account found by phone", account
                else:
                    return False, f"No account found for phone {phone_number}", None
            
            # Fall back to account_id lookup
            if account_id:
                account = db.query(Account).filter(
                    Account.account_id == account_id
                ).first()
                if account:
                    return True, "Account found by ID", account
                else:
                    return False, f"No account found with ID {account_id}", None
            
            return False, "Must provide either account_id or phone_number", None
            
        except Exception as e:
            logger.error(f"Account resolution failed: {str(e)}")
            return False, f"Account resolution failed: {str(e)}", None
    
    @staticmethod
    def acquire_lock(
        db: Session,
        account_id: int,
        request_id: str,
        timeout: int = operation_config.LOCK_TIMEOUT
    ) -> Tuple[bool, str]:
        """
        Acquire exclusive lock on account
        
        Args:
            db: Database session
            account_id: Account ID to lock
            request_id: Unique request identifier
            timeout: Lock expiry time in seconds
            
        Returns:
            (success: bool, message: str)
        """
        try:
            # Check for existing non-expired lock
            existing_lock = db.query(AccountLock).filter(
                AccountLock.account_id == account_id,
                AccountLock.expires_at > datetime.utcnow()
            ).first()
            
            if existing_lock:
                return False, f"Account locked by {existing_lock.lock_holder_server}"
            
            # Clean up expired locks
            db.query(AccountLock).filter(
                AccountLock.account_id == account_id,
                AccountLock.expires_at <= datetime.utcnow()
            ).delete()
            
            # Acquire new lock
            lock = AccountLock(
                account_id=account_id,
                lock_holder_server=server_config.SERVER_ID,
                request_id=request_id,
                lock_type="exclusive",
                expires_at=datetime.utcnow() + timedelta(seconds=timeout),
                reason="Operation in progress"
            )
            db.add(lock)
            db.commit()
            
            logger.info(f"Lock acquired for account {account_id}, request {request_id}")
            return True, "Lock acquired"
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to acquire lock: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def release_lock(
        db: Session,
        account_id: int,
        request_id: str
    ) -> bool:
        """
        Release account lock
        
        Args:
            db: Database session
            account_id: Account ID
            request_id: Request ID that holds the lock
            
        Returns:
            success: bool
        """
        try:
            result = db.query(AccountLock).filter(
                AccountLock.account_id == account_id,
                AccountLock.request_id == request_id
            ).delete()
            db.commit()
            
            if result > 0:
                logger.info(f"Lock released for account {account_id}")
                return True
            return False
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to release lock: {str(e)}")
            return False
    
    @staticmethod
    def withdraw(
        db: Session,
        account_id: int,
        phone_number: str,
        amount: Decimal,
        request_id: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Withdraw amount from account (synchronous operation)
        
        Args:
            db: Database session
            account_id: Account ID
            phone_number: Phone number for audit
            amount: Amount to withdraw
            request_id: Unique request identifier
            
        Returns:
            (success: bool, message: str, response_data: dict)
        """
        lock_acquired = False
        try:
            # Validate amount
            if amount <= 0:
                return False, "Amount must be positive", {}
            
            # Acquire lock
            lock_success, lock_msg = AccountOperations.acquire_lock(
                db, account_id, request_id
            )
            if not lock_success:
                return False, f"Cannot process: {lock_msg}", {}
            
            lock_acquired = True
            
            # Get account with lock
            account = db.query(Account).filter(
                Account.account_id == account_id
            ).with_for_update().first()
            
            if not account:
                return False, "Account not found", {}
            
            if account.account_status != "active":
                return False, f"Account is {account.account_status}", {}
            
            # Check balance
            if account.balance < amount:
                return False, f"Insufficient balance. Have: {account.balance}, Need: {amount}", {
                    "current_balance": float(account.balance)
                }
            
            # Record balance before
            balance_before = account.balance
            
            # Debit account
            account.balance -= amount
            account.last_modified_by_server = server_config.SERVER_ID
            account.version += 1
            db.add(account)
            db.flush()  # Flush to get updated values
            
            # Record transaction
            transaction = Transaction(
                request_id=request_id,
                account_id=account_id,
                phone_number=phone_number,
                transaction_type="withdraw",
                amount=amount,
                balance_before=balance_before,
                balance_after=account.balance,
                status="success",
                server_id=server_config.SERVER_ID,
                processed_at=datetime.utcnow()
            )
            db.add(transaction)
            db.commit()
            
            logger.info(f"Withdrawal successful: {phone_number}, Amount: {amount}, Balance: {account.balance}")
            
            return True, "Withdrawal successful", {
                "transaction_id": transaction.transaction_id,
                "amount": float(amount),
                "balance_after": float(account.balance),
                "timestamp": transaction.created_at.isoformat()
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Withdrawal failed: {str(e)}")
            return False, f"Withdrawal failed: {str(e)}", {}
            
        finally:
            if lock_acquired:
                AccountOperations.release_lock(db, account_id, request_id)
    
    @staticmethod
    def deposit(
        db: Session,
        account_id: int,
        phone_number: str,
        amount: Decimal,
        request_id: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Deposit amount to account (asynchronous notification, synchronous operation)
        
        Args:
            db: Database session
            account_id: Account ID
            phone_number: Phone number
            amount: Amount to deposit
            request_id: Unique request identifier
            
        Returns:
            (success: bool, message: str, response_data: dict)
        """
        lock_acquired = False
        try:
            # Validate amount
            if amount <= 0:
                return False, "Amount must be positive", {}
            
            # Acquire lock
            lock_success, lock_msg = AccountOperations.acquire_lock(
                db, account_id, request_id
            )
            if not lock_success:
                return False, f"Cannot process: {lock_msg}", {}
            
            lock_acquired = True
            
            # Get account with lock
            account = db.query(Account).filter(
                Account.account_id == account_id
            ).with_for_update().first()
            
            if not account:
                return False, "Account not found", {}
            
            if account.account_status != "active":
                return False, f"Account is {account.account_status}", {}
            
            # Record balance before
            balance_before = account.balance
            
            # Credit account
            account.balance += amount
            account.last_modified_by_server = server_config.SERVER_ID
            account.version += 1
            db.add(account)
            db.flush()
            
            # Record transaction
            transaction = Transaction(
                request_id=request_id,
                account_id=account_id,
                phone_number=phone_number,
                transaction_type="deposit",
                amount=amount,
                balance_before=balance_before,
                balance_after=account.balance,
                status="success",
                server_id=server_config.SERVER_ID,
                processed_at=datetime.utcnow()
            )
            db.add(transaction)
            db.commit()
            
            logger.info(f"Deposit successful: {phone_number}, Amount: {amount}, Balance: {account.balance}")
            
            return True, "Deposit received", {
                "transaction_id": transaction.transaction_id,
                "amount": float(amount),
                "balance_after": float(account.balance),
                "timestamp": transaction.created_at.isoformat()
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Deposit failed: {str(e)}")
            return False, f"Deposit failed: {str(e)}", {}
            
        finally:
            if lock_acquired:
                AccountOperations.release_lock(db, account_id, request_id)
    
    @staticmethod
    def check_balance(
        db: Session,
        account_id: int
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check account balance (read-only, no locking)
        
        Args:
            db: Database session
            account_id: Account ID
            
        Returns:
            (success: bool, message: str, response_data: dict)
        """
        try:
            account = db.query(Account).filter(
                Account.account_id == account_id
            ).first()
            
            if not account:
                return False, "Account not found", {}
            
            if account.account_status != "active":
                return False, f"Account is {account.account_status}", {}
            
            return True, "Balance retrieved", {
                "balance": float(account.balance),
                "currency": account.currency,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Balance check failed: {str(e)}")
            return False, f"Balance check failed: {str(e)}", {}
    
    @staticmethod
    def get_last_transactions(
        db: Session,
        account_id: int,
        limit: int = 10
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Get last N transactions for account
        
        Args:
            db: Database session
            account_id: Account ID
            limit: Number of transactions to retrieve
            
        Returns:
            (success: bool, message: str, response_data: dict)
        """
        try:
            transactions = db.query(Transaction).filter(
                Transaction.account_id == account_id
            ).order_by(Transaction.created_at.desc()).limit(limit).all()
            
            txn_list = [
                {
                    "transaction_id": t.transaction_id,
                    "type": t.transaction_type,
                    "amount": float(t.amount),
                    "balance_after": float(t.balance_after),
                    "timestamp": t.created_at.isoformat(),
                    "status": t.status
                }
                for t in transactions
            ]
            
            return True, "Transactions retrieved", {
                "transactions": txn_list,
                "count": len(txn_list)
            }
            
        except Exception as e:
            logger.error(f"Transaction retrieval failed: {str(e)}")
            return False, f"Transaction retrieval failed: {str(e)}", {}
    
    @staticmethod
    def transfer(
        db: Session,
        from_account_id: int,
        from_phone_number: str,
        to_phone_number: str,
        amount: Decimal,
        request_id: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Transfer amount from one account to another
        
        Args:
            db: Database session
            from_account_id: Source account ID
            from_phone_number: Source phone number
            to_phone_number: Destination phone number
            amount: Amount to transfer
            request_id: Unique request identifier
            
        Returns:
            (success: bool, message: str, response_data: dict)
        """
        lock_acquired_from = False
        lock_acquired_to = False
        try:
            # Validate amount
            if amount <= 0:
                return False, "Amount must be positive", {}
            
            # Find both accounts
            from_account = db.query(Account).filter(
                Account.account_id == from_account_id
            ).first()
            
            if not from_account:
                return False, "Source account not found", {}
            
            if from_account.account_status != "active":
                return False, f"Source account is {from_account.account_status}", {}
            
            to_account = db.query(Account).filter(
                Account.phone_number == to_phone_number
            ).first()
            
            if not to_account:
                return False, f"Destination account for {to_phone_number} not found", {}
            
            if to_account.account_status != "active":
                return False, f"Destination account is {to_account.account_status}", {}
            
            # Acquire locks on both accounts (from first, then to)
            lock_success, lock_msg = AccountOperations.acquire_lock(
                db, from_account_id, request_id
            )
            if not lock_success:
                return False, f"Cannot process: {lock_msg}", {}
            lock_acquired_from = True
            
            # Acquire lock on destination account
            to_request_id = f"{request_id}_to"
            lock_success, lock_msg = AccountOperations.acquire_lock(
                db, to_account.account_id, to_request_id
            )
            if not lock_success:
                return False, f"Cannot process destination: {lock_msg}", {}
            lock_acquired_to = True
            
            # Get accounts with locks
            from_account = db.query(Account).filter(
                Account.account_id == from_account_id
            ).with_for_update().first()
            
            to_account = db.query(Account).filter(
                Account.account_id == to_account.account_id
            ).with_for_update().first()
            
            # Check source balance
            if from_account.balance < amount:
                return False, f"Insufficient balance. Have: {from_account.balance}, Need: {amount}", {
                    "current_balance": float(from_account.balance)
                }
            
            # Record balances before
            from_balance_before = from_account.balance
            to_balance_before = to_account.balance
            
            # Execute transfer
            from_account.balance -= amount
            to_account.balance += amount
            from_account.last_modified_by_server = server_config.SERVER_ID
            to_account.last_modified_by_server = server_config.SERVER_ID
            from_account.version += 1
            to_account.version += 1
            
            db.add(from_account)
            db.add(to_account)
            db.flush()
            
            # Record transactions
            from_transaction = Transaction(
                request_id=request_id,
                account_id=from_account_id,
                phone_number=from_phone_number,
                transaction_type="transfer_out",
                amount=amount,
                balance_before=from_balance_before,
                balance_after=from_account.balance,
                status="success",
                description=f"Transfer to {to_phone_number}",
                server_id=server_config.SERVER_ID,
                processed_at=datetime.utcnow()
            )
            
            to_transaction = Transaction(
                request_id=request_id,
                account_id=to_account.account_id,
                phone_number=to_phone_number,
                transaction_type="transfer_in",
                amount=amount,
                balance_before=to_balance_before,
                balance_after=to_account.balance,
                status="success",
                description=f"Transfer from {from_phone_number}",
                server_id=server_config.SERVER_ID,
                processed_at=datetime.utcnow()
            )
            
            db.add(from_transaction)
            db.add(to_transaction)
            db.commit()
            
            logger.info(f"Transfer successful: {from_phone_number} -> {to_phone_number}, Amount: {amount}")
            
            return True, "Transfer successful", {
                "from_phone": from_phone_number,
                "to_phone": to_phone_number,
                "amount": float(amount),
                "from_balance_after": float(from_account.balance),
                "to_balance_after": float(to_account.balance),
                "timestamp": from_transaction.created_at.isoformat()
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Transfer failed: {str(e)}")
            return False, f"Transfer failed: {str(e)}", {}
            
        finally:
            if lock_acquired_from:
                AccountOperations.release_lock(db, from_account_id, request_id)
            if lock_acquired_to:
                # Get the to_account_id again since we may have lost reference
                to_acct = db.query(Account).filter(
                    Account.phone_number == to_phone_number
                ).first()
                if to_acct:
                    AccountOperations.release_lock(db, to_acct.account_id, f"{request_id}_to")
