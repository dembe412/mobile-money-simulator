#!/usr/bin/env python3
"""
Database initialization script
Creates database and all required tables for the Mobile Money System
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import logging
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import text
from config.database import engine, init_db
from config.settings import database_config
from urllib.parse import unquote

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def create_database_if_not_exists():
    """Create the database if it doesn't exist"""
    try:
        logger.info(f"Checking if database '{database_config.DB_NAME}' exists...")
        
        # Connect to default postgres database to create our database
        try:
            conn = psycopg2.connect(
                host=database_config.DB_HOST,
                port=database_config.DB_PORT,
                user=database_config.DB_USER,
                password=database_config.DB_PASSWORD,
                database="postgres"
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            
            # Check if database exists
            cursor.execute(
                f"SELECT 1 FROM pg_database WHERE datname = '{database_config.DB_NAME}';"
            )
            exists = cursor.fetchone()
            
            if not exists:
                logger.info(f"Creating database '{database_config.DB_NAME}'...")
                cursor.execute(f"CREATE DATABASE {database_config.DB_NAME};")
                logger.info(f"✓ Database '{database_config.DB_NAME}' created successfully")
            else:
                logger.info(f"✓ Database '{database_config.DB_NAME}' already exists")
            
            cursor.close()
            conn.close()
            return True
            
        except psycopg2.errors.InvalidPassword:
            logger.error("✗ Invalid PostgreSQL password")
            logger.error(f"  User: {database_config.DB_USER}")
            logger.error(f"  Host: {database_config.DB_HOST}:{database_config.DB_PORT}")
            return False
        except psycopg2.OperationalError as e:
            logger.error(f"✗ Cannot connect to PostgreSQL: {e}")
            logger.error(f"  Host: {database_config.DB_HOST}:{database_config.DB_PORT}")
            logger.error("  Make sure PostgreSQL is running")
            return False
            
    except Exception as e:
        logger.error(f"✗ Error creating database: {e}")
        return False


def main():
    """Initialize the database"""
    logger.info("=" * 70)
    logger.info("Mobile Money System - Database Initialization")
    logger.info("=" * 70)
    logger.info(f"PostgreSQL Host: {database_config.DB_HOST}:{database_config.DB_PORT}")
    logger.info(f"Database: {database_config.DB_NAME}")
    logger.info(f"User: {database_config.DB_USER}")
    logger.info("=" * 70 + "\n")
    
    try:
        # Step 1: Create database if it doesn't exist
        if not create_database_if_not_exists():
            logger.error("\nFailed to create/access database")
            return 1
        
        # Step 2: Test connection to our database
        logger.info("\nTesting connection to mobile_money_system database...")
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.info("✓ Database connection successful")
        except Exception as e:
            logger.error(f"✗ Cannot connect to {database_config.DB_NAME}: {e}")
            return 1
        
        # Step 3: Initialize tables
        logger.info("\nInitializing database schema...")
        init_db()
        logger.info("✓ All tables created successfully")
        
        logger.info("\n" + "=" * 70)
        logger.info("✓ Database setup complete!")
        logger.info("  You can now start the server with: python main.py")
        logger.info("=" * 70)
        
        return 0
        
    except Exception as e:
        logger.error(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
