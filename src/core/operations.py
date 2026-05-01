"""
Core account operations: Withdraw, Deposit, Check Balance
Implements pessimistic locking for concurrency control
Integrates event sourcing for distributed replication
"""
from sqlalchemy.orm import Session
from sqlalchemy import select
from decimal import Decimal
from datetime import datetime, timedelta
import logging
from typing import Tuple, Dict, Any, Optional

from src.models import Account, Transaction, AccountLock, Request
from config.settings import operation_config, server_config
from src.core.events import (
    create_withdraw_event,
    create_deposit_event,
    create_transfer_out_event,
    create_transfer_in_event,
)

logger = logging.getLogger(__name__)


def get_event_sourcing_components():
    """
    Get event sourcing components with delayed import to avoid circular imports.
    
    Returns:
        (event_store, replication_manager, gossip_node) or (None, None, None) if not initialized
    """
    try:
        from src.api.routes import event_store, replication_manager, gossip_node
        return event_store, replication_manager, gossip_node
    except Exception as e:
        logger.debug(f"Event sourcing components not available: {str(e)}")
        return None, None, None


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
            
            logger.debug(f"Lock acquired for account {account_id}, request {request_id}")
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
                logger.debug(f"Lock released for account {account_id}")
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
        Integrates event sourcing for distributed replication
        """
        event_id = None
        try:
            # Validate amount
            if amount <= 0:
                return False, "Amount must be positive", {}
            
            # Fetch the account to check status and balance
            account = db.query(Account).filter(Account.account_id == account_id).first()
            if not account:
                return False, "Account not found", {}
            if account.account_status != "active":
                return False, f"Account is {account.account_status}", {}
            if account.balance < amount:
                return False, f"Insufficient balance. Have: {account.balance}, Need: {amount}", {
                    "current_balance": float(account.balance)
                }

            # Atomic update
            updated_count = db.query(Account).filter(
                Account.account_id == account_id,
                Account.balance >= amount,
                Account.account_status == "active"
            ).update({
                Account.balance: Account.balance - amount,
                Account.version: Account.version + 1,
                Account.last_modified_by_server: server_config.SERVER_ID
            }, synchronize_session="fetch")

            if updated_count == 0:
                db.rollback()
                return False, "Concurrent update prevented withdrawal", {}

            # Fetch updated account for correct balances
            account = db.query(Account).filter(Account.account_id == account_id).first()
            balance_after = account.balance
            balance_before = balance_after + amount
            
            # Event Sourcing: Generate and persist withdraw event
            try:
                event_store, replication_manager, gossip_node = get_event_sourcing_components()
                
                if event_store and replication_manager and gossip_node:
                    # Create withdraw event
                    event = create_withdraw_event(
                        account_id=account_id,
                        request_id=request_id,
                        amount=amount,
                        balance_before=balance_before,
                        balance_after=balance_after,
                        server_id=server_config.SERVER_ID,
                        vector_clock=gossip_node.vector_clock.copy(),
                        phone_number=account.phone_number,
                        account_holder_name=account.account_holder_name,
                    )
                    
                    # Append to event store (non-blocking)
                    event_store.append(event)
                    event_id = event.event_id
                    
                    # Mark as applied locally
                    event_store.mark_applied(event_id)
                    
                    # Queue for replication (non-blocking)
                    replication_manager.queue_event_for_replication(event)
                    
                    # Increment vector clock
                    gossip_node.increment_vector_clock()
            except Exception as e:
                # Graceful fallback: log but continue with DB operation
                logger.warning(f"Event sourcing failed for withdraw (continuing): {str(e)}")
            
            # Record transaction
            transaction = Transaction(
                request_id=request_id,
                account_id=account_id,
                phone_number=phone_number,
                transaction_type="withdraw",
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                status="success",
                server_id=server_config.SERVER_ID,
                processed_at=datetime.utcnow()
            )
            db.add(transaction)
            db.commit()
            
            logger.info(f"Withdrawal: {amount} KES from {phone_number} (Balance: {balance_after})")
            
            response = {
                "transaction_id": transaction.transaction_id,
                "amount": float(amount),
                "balance_after": float(balance_after),
                "timestamp": transaction.created_at.isoformat()
            }
            
            if event_id:
                response["event_id"] = event_id
            
            return True, "Withdrawal successful", response
            
        except Exception as e:
            db.rollback()
            logger.error(f"Withdrawal failed: {str(e)}")
            return False, f"Withdrawal failed: {str(e)}", {}
    
    @staticmethod
    def deposit(
        db: Session,
        account_id: int,
        phone_number: str,
        amount: Decimal,
        request_id: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Deposit amount to account (synchronous operation)
        Integrates event sourcing for distributed replication
        """
        event_id = None
        try:
            # Validate amount
            if amount <= 0:
                return False, "Amount must be positive", {}
            
            # Fetch the account to check status
            account = db.query(Account).filter(Account.account_id == account_id).first()
            if not account:
                return False, "Account not found", {}
            if account.account_status != "active":
                return False, f"Account is {account.account_status}", {}
                
            # Atomic update
            updated_count = db.query(Account).filter(
                Account.account_id == account_id,
                Account.account_status == "active"
            ).update({
                Account.balance: Account.balance + amount,
                Account.version: Account.version + 1,
                Account.last_modified_by_server: server_config.SERVER_ID
            }, synchronize_session="fetch")

            if updated_count == 0:
                db.rollback()
                return False, "Concurrent update prevented deposit", {}

            # Fetch updated account
            account = db.query(Account).filter(Account.account_id == account_id).first()
            balance_after = account.balance
            balance_before = balance_after - amount
            
            # Event Sourcing: Generate and persist deposit event
            try:
                event_store, replication_manager, gossip_node = get_event_sourcing_components()
                
                if event_store and replication_manager and gossip_node:
                    # Create deposit event
                    event = create_deposit_event(
                        account_id=account_id,
                        request_id=request_id,
                        amount=amount,
                        balance_before=balance_before,
                        balance_after=balance_after,
                        server_id=server_config.SERVER_ID,
                        vector_clock=gossip_node.vector_clock.copy(),
                        phone_number=account.phone_number,
                        account_holder_name=account.account_holder_name,
                    )
                    
                    # Append to event store (non-blocking)
                    event_store.append(event)
                    event_id = event.event_id
                    
                    # Mark as applied locally
                    event_store.mark_applied(event_id)
                    
                    # Queue for replication (non-blocking)
                    replication_manager.queue_event_for_replication(event)
                    
                    # Increment vector clock
                    gossip_node.increment_vector_clock()
            except Exception as e:
                # Graceful fallback: log but continue with DB operation
                logger.warning(f"Event sourcing failed for deposit (continuing): {str(e)}")
            
            # Record transaction
            transaction = Transaction(
                request_id=request_id,
                account_id=account_id,
                phone_number=phone_number,
                transaction_type="deposit",
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                status="success",
                server_id=server_config.SERVER_ID,
                processed_at=datetime.utcnow()
            )
            db.add(transaction)
            db.commit()
            
            logger.info(f"Deposit: {amount} KES to {phone_number} (Balance: {balance_after})")
            
            response = {
                "transaction_id": transaction.transaction_id,
                "amount": float(amount),
                "balance_after": float(balance_after),
                "timestamp": transaction.created_at.isoformat()
            }
            
            if event_id:
                response["event_id"] = event_id
            
            return True, "Deposit received", response
            
        except Exception as e:
            db.rollback()
            logger.error(f"Deposit failed: {str(e)}")
            return False, f"Deposit failed: {str(e)}", {}
    
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
        Integrates event sourcing for distributed replication
        """
        out_event_id = None
        in_event_id = None
        try:
            # Validate amount
            if amount <= 0:
                return False, "Amount must be positive", {}
            
            # Find both accounts
            from_account = db.query(Account).filter(Account.account_id == from_account_id).first()
            if not from_account:
                return False, "Source account not found", {}
            if from_account.account_status != "active":
                return False, f"Source account is {from_account.account_status}", {}
            
            to_account = db.query(Account).filter(Account.phone_number == to_phone_number).first()
            if not to_account:
                return False, f"Destination account for {to_phone_number} not found", {}
            if to_account.account_status != "active":
                return False, f"Destination account is {to_account.account_status}", {}
            
            if from_account.balance < amount:
                return False, f"Insufficient balance. Have: {from_account.balance}, Need: {amount}", {
                    "current_balance": float(from_account.balance)
                }
                
            to_account_id = to_account.account_id
            
            # Atomic update for sender
            updated_from = db.query(Account).filter(
                Account.account_id == from_account_id,
                Account.balance >= amount,
                Account.account_status == "active"
            ).update({
                Account.balance: Account.balance - amount,
                Account.version: Account.version + 1,
                Account.last_modified_by_server: server_config.SERVER_ID
            }, synchronize_session="fetch")

            if updated_from == 0:
                db.rollback()
                return False, "Concurrent update prevented transfer (source)", {}
                
            # Atomic update for receiver
            updated_to = db.query(Account).filter(
                Account.account_id == to_account_id,
                Account.account_status == "active"
            ).update({
                Account.balance: Account.balance + amount,
                Account.version: Account.version + 1,
                Account.last_modified_by_server: server_config.SERVER_ID
            }, synchronize_session="fetch")

            if updated_to == 0:
                db.rollback()
                return False, "Concurrent update prevented transfer (destination)", {}

            # Fetch updated accounts
            from_account = db.query(Account).filter(Account.account_id == from_account_id).first()
            to_account = db.query(Account).filter(Account.account_id == to_account_id).first()
            
            from_balance_after = from_account.balance
            from_balance_before = from_balance_after + amount
            to_balance_after = to_account.balance
            to_balance_before = to_balance_after - amount
            
            # Event Sourcing: Generate and persist transfer events
            try:
                event_store, replication_manager, gossip_node = get_event_sourcing_components()
                
                if event_store and replication_manager and gossip_node:
                    vector_clock = gossip_node.vector_clock.copy()
                    
                    out_event = create_transfer_out_event(
                        account_id=from_account_id,
                        request_id=request_id,
                        amount=amount,
                        balance_before=from_balance_before,
                        balance_after=from_balance_after,
                        server_id=server_config.SERVER_ID,
                        vector_clock=vector_clock,
                    )
                    
                    in_event = create_transfer_in_event(
                        account_id=to_account_id,
                        request_id=request_id,
                        amount=amount,
                        balance_before=to_balance_before,
                        balance_after=to_balance_after,
                        server_id=server_config.SERVER_ID,
                        vector_clock=vector_clock,
                    )
                    
                    # Append both events
                    event_store.append(out_event)
                    out_event_id = out_event.event_id
                    
                    event_store.append(in_event)
                    in_event_id = in_event.event_id
                    
                    # Mark both as applied
                    event_store.mark_applied(out_event_id)
                    event_store.mark_applied(in_event_id)
                    
                    # Queue both for replication
                    replication_manager.queue_event_for_replication(out_event)
                    replication_manager.queue_event_for_replication(in_event)
                    
                    # Increment vector clock (once for the pair)
                    gossip_node.increment_vector_clock()
            except Exception as e:
                logger.warning(f"Event sourcing failed for transfer (continuing): {str(e)}")
            
            # Record transactions
            from_transaction = Transaction(
                request_id=request_id,
                account_id=from_account_id,
                phone_number=from_phone_number,
                transaction_type="transfer_out",
                amount=amount,
                balance_before=from_balance_before,
                balance_after=from_balance_after,
                status="success",
                description=f"Transfer to {to_phone_number}",
                server_id=server_config.SERVER_ID,
                processed_at=datetime.utcnow()
            )
            
            to_transaction = Transaction(
                request_id=f"{request_id}_to",
                account_id=to_account_id,
                phone_number=to_phone_number,
                transaction_type="transfer_in",
                amount=amount,
                balance_before=to_balance_before,
                balance_after=to_balance_after,
                status="success",
                description=f"Transfer from {from_phone_number}",
                server_id=server_config.SERVER_ID,
                processed_at=datetime.utcnow()
            )
            
            db.add(from_transaction)
            db.add(to_transaction)
            db.commit()
            
            logger.info(f"Transfer: {amount} KES from {from_phone_number} to {to_phone_number}")
            
            response = {
                "from_phone": from_phone_number,
                "to_phone": to_phone_number,
                "amount": float(amount),
                "from_balance_after": float(from_balance_after),
                "to_balance_after": float(to_balance_after),
                "timestamp": from_transaction.created_at.isoformat()
            }
            
            if out_event_id:
                response["out_event_id"] = out_event_id
            if in_event_id:
                response["in_event_id"] = in_event_id
            
            return True, "Transfer successful", response
            
        except Exception as e:
            db.rollback()
            logger.error(f"Transfer failed: {str(e)}")
            return False, f"Transfer failed: {str(e)}", {}
