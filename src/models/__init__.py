"""
SQLAlchemy ORM Models for Mobile Money System
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, Boolean, Enum, Text, 
    ForeignKey, Index, JSON, LargeBinary, func
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()


class Account(Base):
    """User account"""
    __tablename__ = "accounts"
    
    account_id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    account_holder_name = Column(String(100), nullable=False)
    balance = Column(Numeric(19, 4), nullable=False, default=0)
    currency = Column(String(3), default="KES")
    
    account_status = Column(
        Enum("active", "suspended", "closed", name="account_status_enum"),
        default="active",
        index=True
    )
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_server = Column(String(50))
    last_modified_by_server = Column(String(50))
    version = Column(Integer, default=1)
    
    # Relationships
    transactions = relationship("Transaction", back_populates="account")
    requests = relationship("Request", back_populates="account")
    locks = relationship("AccountLock", back_populates="account", uselist=False)
    
    __table_args__ = (
        Index('idx_phone_status', 'phone_number', 'account_status'),
        Index('idx_account_updated', 'account_id', 'updated_at'),
    )


class TransactionType(str, enum.Enum):
    WITHDRAW = "withdraw"
    DEPOSIT = "deposit"
    TRANSFER = "transfer"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REVERSED = "reversed"


class Transaction(Base):
    """Immutable transaction log"""
    __tablename__ = "transactions"
    
    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(100), unique=True, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.account_id"), nullable=False, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    
    transaction_type = Column(String(20), nullable=False)
    amount = Column(Numeric(19, 4), nullable=False)
    balance_before = Column(Numeric(19, 4), nullable=False)
    balance_after = Column(Numeric(19, 4), nullable=False)
    
    status = Column(
        Enum("pending", "success", "failed", "reversed", name="transaction_status_enum"),
        default="success",
        index=True
    )
    
    description = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed_at = Column(DateTime)
    server_id = Column(String(50), nullable=False, index=True)
    client_reference = Column(String(100))
    reversal_of_transaction = Column(Integer, ForeignKey("transactions.transaction_id"))
    replicated_at = Column(DateTime)
    
    # Relationships
    account = relationship("Account", back_populates="transactions")
    notifications = relationship("Notification", back_populates="transaction")
    
    __table_args__ = (
        Index('idx_account_created', 'account_id', 'created_at'),
        Index('idx_phone_created', 'phone_number', 'created_at'),
    )


class RequestStatus(str, enum.Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Request(Base):
    """Request tracking for idempotency"""
    __tablename__ = "requests"
    
    request_id = Column(String(100), primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.account_id"), nullable=False)
    phone_number = Column(String(20), nullable=False, index=True)
    operation_type = Column(String(50), nullable=False)
    request_data = Column(JSON)
    
    status = Column(
        Enum("received", "processing", "completed", "failed", name="request_status_enum"),
        default="received",
        index=True
    )
    
    response_code = Column(Integer)
    response_data = Column(JSON)
    error_message = Column(Text)
    client_ip = Column(String(45))
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, index=True)
    server_id = Column(String(50), nullable=False, index=True)
    
    # Relationships
    account = relationship("Account", back_populates="requests")
    
    __table_args__ = (
        Index('idx_request_server', 'request_id', 'server_id'),
    )


class AccountLock(Base):
    """Pessimistic locking mechanism"""
    __tablename__ = "account_locks"
    
    lock_id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.account_id"), unique=True, nullable=False)
    lock_holder_server = Column(String(50), nullable=False)
    request_id = Column(String(100), nullable=False)
    lock_type = Column(
        Enum("exclusive", "shared", name="lock_type_enum"),
        default="exclusive"
    )
    acquired_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    reason = Column(String(255))
    
    # Relationships
    account = relationship("Account", back_populates="locks")


class ReplicationLogEntry(Base):
    """P2P replication log for data synchronization"""
    __tablename__ = "replication_log"
    
    replication_id = Column(Integer, primary_key=True, autoincrement=True)
    operation_type = Column(
        Enum("insert", "update", "delete", name="replication_op_enum"),
        nullable=False
    )
    table_name = Column(String(100), nullable=False)
    record_id = Column(String(100), nullable=False)
    data_before = Column(JSON)
    data_after = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    source_server = Column(String(50), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    replicated_to = Column(Text)  # JSON list of servers that received this
    
    __table_args__ = (
        Index('idx_replication_timestamp', 'timestamp'),
        Index('idx_replication_source', 'source_server'),
    )


class ServerStatus(Base):
    """Peer server health and status"""
    __tablename__ = "server_status"
    
    server_id = Column(String(50), primary_key=True)
    server_name = Column(String(100))
    host = Column(String(255))
    port = Column(Integer)
    status = Column(
        Enum("online", "offline", "degraded", name="server_status_enum"),
        default="offline",
        index=True
    )
    last_heartbeat = Column(DateTime, index=True)
    last_sync = Column(DateTime)
    sync_lag_seconds = Column(Integer, default=0)
    total_transactions = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class USSDSession(Base):
    """USSD session management"""
    __tablename__ = "ussd_sessions"
    
    session_id = Column(String(100), primary_key=True)
    phone_number = Column(String(20), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.account_id"), index=True)
    session_state = Column(String(50))
    session_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, index=True)
    server_id = Column(String(50))


class Notification(Base):
    """Notification tracking"""
    __tablename__ = "notifications"
    
    notification_id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(Integer, ForeignKey("transactions.transaction_id"), index=True)
    request_id = Column(String(100), ForeignKey("requests.request_id"))
    phone_number = Column(String(20), nullable=False, index=True)
    notification_type = Column(String(50), index=True)
    message = Column(Text)
    status = Column(
        Enum("pending", "sent", "failed", "read", name="notification_status_enum"),
        default="pending",
        index=True
    )
    delivery_method = Column(String(50))  # sms, push, callback
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    retry_count = Column(Integer, default=0)
    last_retry_at = Column(DateTime)
    
    # Relationships
    transaction = relationship("Transaction", back_populates="notifications")
    
    __table_args__ = (
        Index('idx_phone_status', 'phone_number', 'status'),
    )


class AuditLog(Base):
    """Audit trail"""
    __tablename__ = "audit_log"
    
    audit_id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(100), nullable=False)
    account_id = Column(Integer, index=True)
    request_id = Column(String(100))
    user_info = Column(String(255))
    changes = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    server_id = Column(String(50))
    
    __table_args__ = (
        Index('idx_action_created', 'action', 'created_at'),
    )
