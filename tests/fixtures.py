"""
Pytest fixtures and test utilities for mobile-money-simulator.
Provides reusable test data and cleanup functions that preserve production/staging data
while isolating test data for independent test execution.
"""
import pytest
import logging
from decimal import Decimal
from datetime import datetime
from typing import Generator
from sqlalchemy.orm import Session

from config.database import SessionLocal, init_db
from config.settings import app_config
from src.models import (
    Account, Transaction, Request, ServerStatus, USSDSession,
    Notification, AuditLog, Event, EventReplicationState, AccountLock
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def db_session() -> Generator[Session, None, None]:
    """
    Session-scoped database session for test suite initialization.
    Creates database schema once at test session start.
    
    Yields:
        SQLAlchemy Session instance
    """
    # Initialize database schema before tests
    init_db()
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db(db_session: Session) -> Generator[Session, None, None]:
    """
    Function-scoped database session with automatic cleanup.
    Each test gets a fresh session and cleans up test data afterwards.
    
    Yields:
        SQLAlchemy Session instance
    """
    # Cleanup any previous test data before this test
    cleanup_test_data(db_session)
    
    yield db_session
    
    # Cleanup test data after test completes
    cleanup_test_data(db_session)


@pytest.fixture(scope="function")
def test_account(db: Session) -> Account:
    """
    Create a test account with default balance.
    Automatically cleaned up after test via db fixture.
    
    Args:
        db: Database session (function-scoped)
        
    Returns:
        Account instance ready for testing
    """
    account = Account(
        phone_number="254712345678",
        account_holder_name="Test User",
        balance=Decimal("10000.00"),
        currency="KES",
        account_status="active",
        created_by_server="test_server",
        last_modified_by_server="test_server",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    
    logger.info(f"Created test account: {account.account_id} ({account.phone_number})")
    return account


@pytest.fixture(scope="function")
def test_account_2(db: Session) -> Account:
    """
    Create a second test account for transfer tests.
    
    Args:
        db: Database session (function-scoped)
        
    Returns:
        Account instance ready for testing
    """
    account = Account(
        phone_number="254787654321",
        account_holder_name="Test User 2",
        balance=Decimal("5000.00"),
        currency="KES",
        account_status="active",
        created_by_server="test_server",
        last_modified_by_server="test_server",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    
    logger.info(f"Created test account 2: {account.account_id} ({account.phone_number})")
    return account


@pytest.fixture(scope="function")
def test_transaction(db: Session, test_account: Account) -> Transaction:
    """
    Create a test transaction for the test account.
    
    Args:
        db: Database session (function-scoped)
        test_account: Test account fixture
        
    Returns:
        Transaction instance ready for testing
    """
    transaction = Transaction(
        request_id="test_request_001",
        account_id=test_account.account_id,
        phone_number=test_account.phone_number,
        transaction_type="withdraw",
        amount=Decimal("1000.00"),
        balance_before=Decimal("10000.00"),
        balance_after=Decimal("9000.00"),
        status="success",
        description="Test withdrawal",
        server_id="test_server",
        client_reference="test_client_ref",
        created_at=datetime.utcnow(),
        processed_at=datetime.utcnow(),
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    
    logger.info(f"Created test transaction: {transaction.transaction_id}")
    return transaction


@pytest.fixture(scope="function")
def test_request(db: Session, test_account: Account) -> Request:
    """
    Create a test request for idempotency testing.
    
    Args:
        db: Database session (function-scoped)
        test_account: Test account fixture
        
    Returns:
        Request instance ready for testing
    """
    request = Request(
        request_id="test_req_withdraw_001",
        account_id=test_account.account_id,
        phone_number=test_account.phone_number,
        operation_type="withdraw",
        request_data={"amount": "1000.00"},
        status="completed",
        response_code=200,
        response_data={"balance_after": "9000.00"},
        client_ip="127.0.0.1",
        server_id="test_server",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    
    logger.info(f"Created test request: {request.request_id}")
    return request


@pytest.fixture(scope="function")
def test_ussd_session(db: Session, test_account: Account) -> USSDSession:
    """
    Create a test USSD session.
    
    Args:
        db: Database session (function-scoped)
        test_account: Test account fixture
        
    Returns:
        USSDSession instance ready for testing
    """
    session = USSDSession(
        session_id="test_ussd_session_001",
        phone_number=test_account.phone_number,
        account_id=test_account.account_id,
        session_state="active",
        session_data={"menu_level": 1},
        server_id="test_server",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        expires_at=datetime.utcnow(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    
    logger.info(f"Created test USSD session: {session.session_id}")
    return session


def cleanup_test_data(db: Session) -> dict:
    """
    Clean up test-generated data while preserving production data.
    
    This function deletes records created during testing while preserving:
    - All transactions (immutable audit trail)
    - All events (event sourcing records)
    - All audit logs (compliance/audit trail)
    - All data not explicitly marked as test data
    
    Uses phone number pattern matching to identify test data:
    - Phone numbers starting with "2547" (test range)
    - Request IDs starting with "test_"
    
    Args:
        db: Database session
        
    Returns:
        Dictionary with cleanup statistics
    """
    stats = {
        "accounts_deleted": 0,
        "requests_deleted": 0,
        "locks_deleted": 0,
        "ussd_sessions_deleted": 0,
        "notifications_deleted": 0,
        "server_statuses_deleted": 0,
    }
    
    try:
        # Delete test USSD sessions (by phone number pattern)
        test_sessions = db.query(USSDSession).filter(
            USSDSession.phone_number.like("2547%")
        ).all()
        for session in test_sessions:
            db.delete(session)
        stats["ussd_sessions_deleted"] = len(test_sessions)
        
        # Delete test notifications (by request_id pattern or phone pattern)
        test_notifications = db.query(Notification).filter(
            (Notification.request_id.like("test_%")) |
            (Notification.phone_number.like("2547%"))
        ).all()
        for notif in test_notifications:
            db.delete(notif)
        stats["notifications_deleted"] = len(test_notifications)
        
        # Delete test requests (by request_id pattern or phone pattern)
        test_requests = db.query(Request).filter(
            (Request.request_id.like("test_%")) |
            (Request.phone_number.like("2547%"))
        ).all()
        for request in test_requests:
            db.delete(request)
        stats["requests_deleted"] = len(test_requests)
        
        # Delete test account locks (before deleting accounts)
        test_locks = db.query(AccountLock).join(Account).filter(
            Account.phone_number.like("2547%")
        ).all()
        for lock in test_locks:
            db.delete(lock)
        stats["locks_deleted"] = len(test_locks)
        
        # Delete test server statuses (created during tests)
        test_server_statuses = db.query(ServerStatus).filter(
            ServerStatus.server_id.like("test_%")
        ).all()
        for status in test_server_statuses:
            db.delete(status)
        stats["server_statuses_deleted"] = len(test_server_statuses)
        
        # Delete test accounts (by phone number pattern)
        test_accounts = db.query(Account).filter(
            Account.phone_number.like("2547%")
        ).all()
        for account in test_accounts:
            db.delete(account)
        stats["accounts_deleted"] = len(test_accounts)
        
        # Commit all deletions
        db.commit()
        
        logger.info(f"Test data cleanup completed. Deleted: {stats}")
        return stats
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error during test data cleanup: {e}")
        raise
