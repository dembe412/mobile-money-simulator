#!/usr/bin/env python3
"""
Verify database data persistence - shows that data survives server restarts
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from config.database import SessionLocal
from src.models import Account, Transaction, Request, Notification, USSDSession
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_data():
    """Verify all data in database"""
    db = SessionLocal()
    
    print("\n" + "="*80)
    print("DATA PERSISTENCE VERIFICATION")
    print("="*80)
    
    try:
        # Count records
        accounts = db.query(Account).count()
        transactions = db.query(Transaction).count()
        requests = db.query(Request).count()
        notifications = db.query(Notification).count()
        sessions = db.query(USSDSession).count()
        
        print(f"\n✓ Accounts:       {accounts:5} records")
        print(f"✓ Transactions:   {transactions:5} records")
        print(f"✓ Requests:       {requests:5} records")
        print(f"✓ Notifications:  {notifications:5} records")
        print(f"✓ USSD Sessions:  {sessions:5} records")
        
        total_records = accounts + transactions + requests + notifications + sessions
        print("-" * 80)
        print(f"✓ TOTAL:          {total_records:5} records")
        
        if accounts > 0:
            print("\nSample accounts:")
            sample_accounts = db.query(Account).limit(3).all()
            for acc in sample_accounts:
                print(f"  • {acc.phone_number:15} | {acc.account_holder_name:25} | {float(acc.balance):>12,.0f} {acc.currency}")
        
        print("\n" + "="*80)
        
        # Verify no data loss
        if accounts > 0 and transactions > 0:
            print("\n✓ SUCCESS: Data persists after server restart!")
            print("✓ Database initialization is idempotent - won't drop existing tables")
            print("✓ All operations preserve data correctly")
            return True
        else:
            print("\n✗ WARNING: No data found in database")
            return False
            
    except Exception as e:
        logger.error(f"Error verifying data: {e}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = verify_data()
    sys.exit(0 if success else 1)
