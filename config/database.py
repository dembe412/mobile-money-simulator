"""
Database connection and session management
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
import logging
from config.settings import database_config

logger = logging.getLogger(__name__)

# Create database engine
engine = create_engine(
    database_config.DATABASE_URL,
    echo=database_config.ECHO_SQL,
    poolclass=NullPool,  # Disable connection pooling for distributed scenarios
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Dependency injection for database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Set timezone on connection"""
    pass


def init_db():
    """Initialize database (create all tables)"""
    from src.models import Base
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")


def drop_db():
    """Drop all tables (for testing)"""
    from src.models import Base
    Base.metadata.drop_all(bind=engine)
    logger.info("Database dropped")
