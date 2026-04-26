"""
Database connection and session management — SQLite edition.
Each server node gets its own isolated SQLite file.
No PostgreSQL, no Docker, no external services needed.
"""
from sqlalchemy import create_engine, event, text, inspect
from sqlalchemy.orm import sessionmaker, Session
import logging
from config.settings import database_config, app_config

logger = logging.getLogger(__name__)


# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_engine(
    database_config.DATABASE_URL,
    echo=database_config.ECHO_SQL,
    connect_args={
        "check_same_thread": False,   # Required for SQLite + threads
        "timeout": 30,                # Wait up to 30s if DB is locked
    },
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    """Enable WAL mode and foreign keys on every new SQLite connection."""
    cursor = dbapi_conn.cursor()
    # WAL mode: readers don't block writers and vice-versa (much better concurrency)
    cursor.execute("PRAGMA journal_mode=WAL")
    # Enforce foreign-key constraints
    cursor.execute("PRAGMA foreign_keys=ON")
    # Slightly relaxed fsync — good for dev; change to FULL for production
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def get_db() -> Session:
    """FastAPI dependency injection for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(force_reset: bool = False):
    """
    Create all tables for this server's SQLite database.

    - Idempotent: safe to call multiple times.
    - force_reset=True drops all tables first (useful for clean test runs).
    """
    from src.models import Base  # local import avoids circular deps

    db_path = database_config.DB_PATH
    logger.info(f"Initializing database at: {db_path}")

    if force_reset:
        logger.warning("force_reset=True: dropping all tables")
        Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)
    logger.info("✓ Database schema ready")


def drop_db():
    """Drop all tables (for testing only)."""
    from src.models import Base
    Base.metadata.drop_all(bind=engine)
    logger.info("Database dropped")
