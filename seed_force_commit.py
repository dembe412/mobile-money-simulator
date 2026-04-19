#!/usr/bin/env python3
"""
Robust database seeding with Ugandan test data - Force commit version
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import logging
from decimal import Decimal
from sqlalchemy import text
from config.database import SessionLocal, engine
from src.models import (
    Account, Transaction, Request, ServerStatus, 
    USSDSession, Notification, ReplicationLogEntry
)
from config.settings import server_config
from datetime import datetime, timedelta
import random
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Ugandan test data
UGANDAN_ACCOUNTS = [
    ("0752235731", "John Musoke", Decimal("250000.00")),
    ("0701234567", "Sarah Namukwaya", Decimal("500000.00")),
    ("0777654321", "David Kipchoge", Decimal("1000000.00")),
    ("0701112222", "Grace Achieng", Decimal("750000.00")),
    ("0703334444", "Samuel Okonkwo", Decimal("2000000.00")),
    ("0705556666", "Amina Hassan", Decimal("350000.00")),
    ("0707778888", "Christopher Wombat", Decimal("1500000.00")),
    ("0709990000", "Victoria Kabuubi", Decimal("600000.00")),
    ("0711223344", "Paul Okello", Decimal("450000.00")),
    ("0713334455", "Florence Nalweyiso", Decimal("1200000.00")),
]

TRANSACTION_DESCRIPTIONS = [
    "Payment for goods",
    "Salary deposit",
    "Utility bill payment",
    "School fees",
    "Medical expenses",
    "Rent payment",
    "Transfer to family",
    "Business payment",
    "Loan repayment",
    "Mobile airtime",
]


def seed_accounts(db):
    """Add test accounts to database"""
    logger.info("Seeding accounts...")
    added_count = 0
    
    for phone, name, balance in UGANDAN_ACCOUNTS:
        # Check if account already exists
        existing = db.query(Account).filter(
            Account.phone_number == phone
        ).first()
        
        if existing:
            logger.info(f"  ⊘ Account {phone} already exists")
            continue
        
        account = Account(
            phone_number=phone,
            account_holder_name=name,
            balance=balance,
            currency="UGX",
            account_status="active",
            created_by_server=server_config.SERVER_ID,
            last_modified_by_server=server_config.SERVER_ID
        )
        
        db.add(account)
        added_count += 1
        logger.info(f"  ✓ {phone} | {name:25} | {balance:>12.0f} UGX")
    
    # Force commit with explicit transaction
    if added_count > 0:
        try:
            db.commit()
            logger.info(f"✓ Committed {added_count} accounts")
        except Exception as e:
            logger.error(f"Error committing accounts: {e}")
            db.rollback()
    
    return added_count


def seed_transactions(db):
    """Add sample transactions to accounts"""
    logger.info("\nSeeding transactions...")
    added_count = 0
    
    accounts = db.query(Account).all()
    if not accounts:
        logger.warning("  ⊘ No accounts found")
        return added_count
    
    # Create transactions for each account
    for account in accounts:
        current_balance = account.balance
        
        # Create 3-5 transactions per account
        num_transactions = random.randint(3, 5)
        
        for i in range(num_transactions):
            amount = Decimal(str(random.randint(10000, 500000)))
            balance_before = current_balance
            
            # Randomly deposit or withdraw
            if random.choice([True, False]) and balance_before >= amount:
                current_balance -= amount
                trans_type = random.choice(["withdraw", "transfer"])
            else:
                current_balance += amount
                trans_type = "deposit"
            
            # Create transaction
            trans = Transaction(
                request_id=f"seed_{account.phone_number}_{i}_{int(datetime.utcnow().timestamp() * 1000)}",
                account_id=account.account_id,
                phone_number=account.phone_number,
                transaction_type=trans_type,
                amount=amount,
                balance_before=balance_before,
                balance_after=current_balance,
                status="success",
                description=random.choice(TRANSACTION_DESCRIPTIONS),
                server_id=server_config.SERVER_ID,
                processed_at=datetime.utcnow() - timedelta(days=random.randint(0, 30))
            )
            
            db.add(trans)
            added_count += 1
        
        logger.info(f"  ✓ {account.phone_number} | Created {num_transactions} transactions")
    
    # Force commit
    if added_count > 0:
        try:
            db.commit()
            logger.info(f"✓ Committed {added_count} transactions")
        except Exception as e:
            logger.error(f"Error committing transactions: {e}")
            db.rollback()
    
    return added_count


def seed_requests(db):
    """Add sample requests (API call history)"""
    logger.info("\nSeeding requests...")
    added_count = 0
    
    accounts = db.query(Account).all()
    if not accounts:
        logger.warning("  ⊘ No accounts found")
        return added_count
    
    operations = ["deposit", "withdraw", "balance_check", "transfer"]
    
    for account in accounts:
        # Create 2-4 requests per account
        num_requests = random.randint(2, 4)
        
        for i in range(num_requests):
            operation = random.choice(operations)
            amount = Decimal(str(random.randint(50000, 1000000)))
            
            request = Request(
                request_id=f"req_{account.phone_number}_{i}_{int(datetime.utcnow().timestamp() * 1000)}",
                account_id=account.account_id,
                phone_number=account.phone_number,
                operation_type=operation,
                request_data={
                    "amount": str(amount),
                    "description": "Test API request"
                },
                status="completed",
                response_code=200,
                response_data={
                    "transaction_id": f"txn_{i}",
                    "amount": str(amount),
                    "balance_after": str(account.balance + amount if operation == "deposit" else account.balance - amount)
                },
                client_ip="127.0.0.1",
                expires_at=datetime.utcnow() + timedelta(hours=24),
                server_id=server_config.SERVER_ID
            )
            
            db.add(request)
            added_count += 1
        
        logger.info(f"  ✓ {account.phone_number} | Created {num_requests} requests")
    
    # Force commit
    if added_count > 0:
        try:
            db.commit()
            logger.info(f"✓ Committed {added_count} requests")
        except Exception as e:
            logger.error(f"Error committing requests: {e}")
            db.rollback()
    
    return added_count


def seed_ussd_sessions(db):
    """Add sample USSD sessions"""
    logger.info("\nSeeding USSD sessions...")
    added_count = 0
    
    accounts = db.query(Account).all()
    if not accounts:
        logger.warning("  ⊘ No accounts found")
        return added_count
    
    session_states = ["menu", "amount_entry", "confirmation", "completed"]
    
    for account in accounts:
        # Create 1-3 sessions per account
        num_sessions = random.randint(1, 3)
        
        for i in range(num_sessions):
            session = USSDSession(
                session_id=f"ussd_{account.phone_number}_{i}_{int(datetime.utcnow().timestamp() * 1000)}",
                phone_number=account.phone_number,
                account_id=account.account_id,
                session_state=random.choice(session_states),
                session_data={
                    "menu_level": random.randint(1, 5),
                    "last_action": "deposit" if random.choice([True, False]) else "withdraw",
                    "timestamp": datetime.utcnow().isoformat()
                },
                expires_at=datetime.utcnow() + timedelta(minutes=30),
                server_id=server_config.SERVER_ID
            )
            
            db.add(session)
            added_count += 1
        
        logger.info(f"  ✓ {account.phone_number} | Created {num_sessions} USSD sessions")
    
    # Force commit
    if added_count > 0:
        try:
            db.commit()
            logger.info(f"✓ Committed {added_count} USSD sessions")
        except Exception as e:
            logger.error(f"Error committing USSD sessions: {e}")
            db.rollback()
    
    return added_count


def seed_notifications(db):
    """Add sample notifications"""
    logger.info("\nSeeding notifications...")
    added_count = 0
    
    # Get requests instead of transactions
    requests = db.query(Request).all()
    if not requests:
        logger.warning("  ⊘ No requests found")
        return added_count
    
    notification_types = ["deposit_confirmation", "withdrawal_confirmation", "balance_alert", "transaction_failed"]
    
    # Add notifications for requests
    for request in requests[:min(20, len(requests))]:
        # Find a transaction for this request if it exists
        transaction = db.query(Transaction).filter(
            Transaction.request_id == request.request_id
        ).first()
        
        notification = Notification(
            transaction_id=transaction.transaction_id if transaction else None,
            request_id=request.request_id,  # Use the request_id that actually exists
            phone_number=request.phone_number,
            notification_type=random.choice(notification_types),
            message=f"Your {request.operation_type} request has been processed",
            status=random.choice(["sent", "pending", "failed"]),
            delivery_method="sms",
            sent_at=datetime.utcnow() - timedelta(hours=random.randint(1, 24)),
            retry_count=random.randint(0, 3)
        )
        
        db.add(notification)
        added_count += 1
        logger.info(f"  ✓ {request.phone_number} | Notification: {notification.notification_type}")
    
    # Force commit
    if added_count > 0:
        try:
            db.commit()
            logger.info(f"✓ Committed {added_count} notifications")
        except Exception as e:
            logger.error(f"Error committing notifications: {e}")
            db.rollback()
    
    return added_count


def main():
    """Main seeding function"""
    logger.info("=" * 80)
    logger.info("Mobile Money System - Ugandan Test Data Seeding")
    logger.info("=" * 80)
    
    db = SessionLocal()
    
    try:
        results = {
            "accounts": seed_accounts(db),
            "transactions": seed_transactions(db),
            "requests": seed_requests(db),
            "ussd_sessions": seed_ussd_sessions(db),
            "notifications": seed_notifications(db),
        }
        
        # Display summary
        logger.info("\n" + "=" * 80)
        logger.info("SEEDING SUMMARY")
        logger.info("=" * 80)
        for table, count in results.items():
            logger.info(f"  {table:20} | {count:5} rows added")
        logger.info("=" * 80)
        
        # Display data statistics
        logger.info("\nDATA STATISTICS (VERIFYING DATA WAS SAVED)")
        logger.info("-" * 80)
        
        account_count = db.query(Account).count()
        transaction_count = db.query(Transaction).count()
        request_count = db.query(Request).count()
        notification_count = db.query(Notification).count()
        session_count = db.query(USSDSession).count()
        
        logger.info(f"  Total Accounts:           {account_count:5}")
        logger.info(f"  Total Transactions:       {transaction_count:5}")
        logger.info(f"  Total Requests:           {request_count:5}")
        logger.info(f"  Total Notifications:      {notification_count:5}")
        logger.info(f"  Total USSD Sessions:      {session_count:5}")
        logger.info("-" * 80)
        
        # Show sample accounts
        if account_count > 0:
            logger.info("\nSAMPLE ACCOUNTS IN DATABASE")
            logger.info("-" * 80)
            accounts = db.query(Account).all()
            for acc in accounts:
                logger.info(f"  {acc.phone_number:15} | {acc.account_holder_name:25} | {acc.balance:>12.0f} UGX | {acc.account_status}")
            logger.info("-" * 80)
        
        logger.info("\n✓ Database seeding complete!")
        logger.info("=" * 80)
        
        return 0
        
    except Exception as e:
        logger.error(f"\n✗ Error seeding data: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return 1
    
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
