"""
Database connection and session management
"""
from sqlalchemy import create_engine, event, text, inspect
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


def init_db(force_reset=False):
    """
    Initialize database (create all tables if they don't exist)
    
    Args:
        force_reset: If True, drop all tables and recreate. Default False (idempotent)
    """
    from src.models import Base
    try:
        # Check if tables already exist (idempotent behavior)
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        if existing_tables and not force_reset:
            logger.info(f"Database already initialized. Found {len(existing_tables)} existing tables. Skipping initialization.")
            return
        
        if force_reset and existing_tables:
            # Drop all tables using CASCADE (drops dependent indexes, constraints, etc.)
            with engine.begin() as conn:
                # First, drop all views (if any)
                conn.execute(text("""
                    DO $$ 
                    DECLARE 
                        r RECORD;
                    BEGIN
                        FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') 
                        LOOP
                            EXECUTE 'DROP TABLE IF EXISTS "' || r.tablename || '" CASCADE';
                        END LOOP;
                    END $$;
                """))
                logger.info("Dropped all existing tables and related objects")
        
        # Drop all indexes to avoid conflicts with existing indexes
        with engine.begin() as conn:
            try:
                conn.execute(text("""
                    DO $$ 
                    DECLARE 
                        r RECORD;
                    BEGIN
                        FOR r IN (SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND indexname NOT LIKE 'pg_%') 
                        LOOP
                            EXECUTE 'DROP INDEX IF EXISTS "' || r.indexname || '" CASCADE';
                        END LOOP;
                    END $$;
                """))
                logger.info("Cleaned up existing indexes")
            except Exception as idx_error:
                logger.debug(f"Index cleanup (non-critical): {idx_error}")
        
        # Create all tables fresh (creates only non-existent tables)
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise


def drop_db():
    """Drop all tables (for testing)"""
    from src.models import Base
    Base.metadata.drop_all(bind=engine)
    logger.info("Database dropped")
