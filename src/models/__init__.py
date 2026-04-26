"""
SQLAlchemy ORM Models for Mobile Money System.
Uses only SQLite-compatible column types (no PostgreSQL-specific Enums).
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, Boolean, Text,
    ForeignKey, Index, JSON
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class Account(Base):
    """User account"""
    __tablename__ = "accounts"

    account_id          = Column(Integer, primary_key=True, autoincrement=True)
    phone_number        = Column(String(20), unique=True, nullable=False, index=True)
    account_holder_name = Column(String(100), nullable=False)
    balance             = Column(Numeric(19, 4), nullable=False, default=0)
    currency            = Column(String(3), default="KES")
    account_status      = Column(String(20), default="active", index=True)  # active|suspended|closed

    created_at              = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at              = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_server       = Column(String(50))
    last_modified_by_server = Column(String(50))
    version                 = Column(Integer, default=1)

    # Relationships
    transactions = relationship("Transaction", back_populates="account")
    requests     = relationship("Request",     back_populates="account")
    locks        = relationship("AccountLock", back_populates="account", uselist=False)

    __table_args__ = (
        Index("idx_phone_status",   "phone_number", "account_status"),
        Index("idx_account_updated","account_id",   "updated_at"),
    )


class Transaction(Base):
    """Immutable transaction log"""
    __tablename__ = "transactions"

    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    request_id     = Column(String(100), unique=True, nullable=False)
    account_id     = Column(Integer, ForeignKey("accounts.account_id"), nullable=False, index=True)
    phone_number   = Column(String(20), nullable=False, index=True)

    transaction_type = Column(String(20), nullable=False)   # withdraw|deposit|transfer_out|transfer_in
    amount           = Column(Numeric(19, 4), nullable=False)
    balance_before   = Column(Numeric(19, 4), nullable=False)
    balance_after    = Column(Numeric(19, 4), nullable=False)
    status           = Column(String(20), default="success", index=True)  # pending|success|failed|reversed

    description    = Column(String(255))
    created_at     = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed_at   = Column(DateTime)
    server_id      = Column(String(50), nullable=False, index=True)
    client_reference = Column(String(100))
    reversal_of_transaction = Column(Integer, ForeignKey("transactions.transaction_id"))
    replicated_at  = Column(DateTime)

    account       = relationship("Account",      back_populates="transactions")
    notifications = relationship("Notification", back_populates="transaction")

    __table_args__ = (
        Index("idx_account_created", "account_id",   "created_at"),
        Index("idx_phone_created",   "phone_number",  "created_at"),
    )


class Request(Base):
    """Request tracking for idempotency"""
    __tablename__ = "requests"

    request_id     = Column(String(100), primary_key=True)
    account_id     = Column(Integer, ForeignKey("accounts.account_id"), nullable=False)
    phone_number   = Column(String(20), nullable=False, index=True)
    operation_type = Column(String(50), nullable=False)
    request_data   = Column(JSON)
    status         = Column(String(20), default="received", index=True)  # received|processing|completed|failed
    response_code  = Column(Integer)
    response_data  = Column(JSON)
    error_message  = Column(Text)
    client_ip      = Column(String(45))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, index=True)
    server_id  = Column(String(50), nullable=False, index=True)

    account = relationship("Account", back_populates="requests")

    __table_args__ = (
        Index("idx_request_server", "request_id", "server_id"),
    )


class AccountLock(Base):
    """Pessimistic locking mechanism"""
    __tablename__ = "account_locks"

    lock_id             = Column(Integer, primary_key=True, autoincrement=True)
    account_id          = Column(Integer, ForeignKey("accounts.account_id"), unique=True, nullable=False)
    lock_holder_server  = Column(String(50), nullable=False)
    request_id          = Column(String(100), nullable=False)
    lock_type           = Column(String(20), default="exclusive")   # exclusive|shared
    acquired_at         = Column(DateTime, default=datetime.utcnow)
    expires_at          = Column(DateTime, nullable=False, index=True)
    reason              = Column(String(255))

    account = relationship("Account", back_populates="locks")


class ServerStatus(Base):
    """Peer server health and status"""
    __tablename__ = "server_status"

    server_id        = Column(String(50), primary_key=True)
    server_name      = Column(String(100))
    host             = Column(String(255))
    port             = Column(Integer)
    status           = Column(String(20), default="offline", index=True)  # online|offline|degraded
    last_heartbeat   = Column(DateTime, index=True)
    last_sync        = Column(DateTime)
    sync_lag_seconds = Column(Integer, default=0)
    total_transactions = Column(Integer, default=0)
    error_count      = Column(Integer, default=0)

    peer_vector_clock    = Column(JSON)
    sync_position        = Column(Integer, default=0)
    ops_behind           = Column(Integer, default=0)
    last_event_received  = Column(DateTime)
    pending_events_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class USSDSession(Base):
    """USSD session management"""
    __tablename__ = "ussd_sessions"

    session_id   = Column(String(100), primary_key=True)
    phone_number = Column(String(20), nullable=False, index=True)
    account_id   = Column(Integer, ForeignKey("accounts.account_id"), index=True)
    session_state = Column(String(50))
    session_data  = Column(JSON)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at    = Column(DateTime, index=True)
    server_id     = Column(String(50))


class Notification(Base):
    """Notification tracking"""
    __tablename__ = "notifications"

    notification_id   = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id    = Column(Integer, ForeignKey("transactions.transaction_id"), index=True)
    request_id        = Column(String(100), ForeignKey("requests.request_id"))
    phone_number      = Column(String(20), nullable=False, index=True)
    notification_type = Column(String(50), index=True)
    message           = Column(Text)
    status            = Column(String(20), default="pending", index=True)  # pending|sent|failed|read
    delivery_method   = Column(String(50))
    sent_at           = Column(DateTime)
    created_at        = Column(DateTime, default=datetime.utcnow)
    retry_count       = Column(Integer, default=0)
    last_retry_at     = Column(DateTime)

    transaction = relationship("Transaction", back_populates="notifications")

    __table_args__ = (
        Index("idx_notification_phone_status", "phone_number", "status"),
    )


class AuditLog(Base):
    """Audit trail"""
    __tablename__ = "audit_log"

    audit_id   = Column(Integer, primary_key=True, autoincrement=True)
    action     = Column(String(100), nullable=False)
    account_id = Column(Integer, index=True)
    request_id = Column(String(100))
    user_info  = Column(String(255))
    changes    = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    server_id  = Column(String(50))

    __table_args__ = (
        Index("idx_action_created", "action", "created_at"),
    )


class Event(Base):
    """Immutable event log for event sourcing"""
    __tablename__ = "events"

    event_id    = Column(String(100), primary_key=True)
    event_type  = Column(String(50), nullable=False, index=True)
    account_id  = Column(Integer, ForeignKey("accounts.account_id"), nullable=False, index=True)
    request_id  = Column(String(100), unique=True, nullable=False, index=True)

    amount         = Column(Numeric(19, 4), nullable=False)
    balance_before = Column(Numeric(19, 4), nullable=False)
    balance_after  = Column(Numeric(19, 4), nullable=False)

    vector_clock     = Column(JSON, nullable=False)
    server_id        = Column(String(50), nullable=False, index=True)
    timestamp        = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    client_reference = Column(String(100))

    is_applied    = Column(Boolean, default=False, index=True)
    is_replicated = Column(Boolean, default=False, index=True)
    replicated_to = Column(JSON)  # {server_id: iso_timestamp}

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_event_account_ts", "account_id", "timestamp"),
        Index("idx_event_server_ts",  "server_id",  "timestamp"),
    )


class WriteAheadLog(Base):
    """Write-ahead log for durability and crash recovery"""
    __tablename__ = "write_ahead_log"

    log_id            = Column(Integer, primary_key=True, autoincrement=True)
    event_id          = Column(String(100), ForeignKey("events.event_id"), nullable=False, unique=True)
    status            = Column(String(20), default="pending", nullable=False, index=True)  # pending|applied|replicated
    replicated_count  = Column(Integer, default=0)
    required_replicas = Column(Integer, default=1)
    created_at        = Column(DateTime, default=datetime.utcnow)
    applied_at        = Column(DateTime)
    replicated_at     = Column(DateTime)

    __table_args__ = (
        Index("idx_wal_status_created", "status", "created_at"),
    )


class EventReplicationState(Base):
    """Track which events have been replicated to which peers"""
    __tablename__ = "event_replication_state"

    replication_state_id = Column(Integer, primary_key=True, autoincrement=True)
    event_id  = Column(String(100), ForeignKey("events.event_id"), nullable=False, index=True)
    server_id = Column(String(50), nullable=False, index=True)
    acked     = Column(Boolean, default=False)
    acked_at  = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_replication_event_server", "event_id", "server_id"),
    )
