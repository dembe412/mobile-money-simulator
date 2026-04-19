"""
Main application entry point
Starts the Mobile Money Server
"""
import uvicorn
import logging
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import server_config, app_config, database_config
from config.database import init_db, SessionLocal
from config.logging_config import setup_logging
from src.api.routes import app

# Configure enhanced logging with server context
logger = setup_logging(
    server_id=server_config.SERVER_ID,
    server_port=server_config.SERVER_PORT,
    log_level=app_config.LOG_LEVEL
)


def main():
    """Start the server"""
    logger.info("=" * 70)
    logger.info(f"Starting {app_config.APP_NAME} v{app_config.APP_VERSION}")
    logger.info("=" * 70)
    
    logger.info("SERVER CONFIGURATION:")
    logger.info(f"  Server ID:        {server_config.SERVER_ID}")
    logger.info(f"  Server Name:      {server_config.SERVER_NAME}")
    logger.info(f"  Address:          {server_config.SERVER_HOST}:{server_config.SERVER_PORT}")
    logger.info(f"  Environment:      {app_config.APP_ENV}")
    logger.info("=" * 70)
    logger.info("DATABASE CONFIGURATION:")
    logger.info(f"  Host:             {database_config.DB_HOST}:{database_config.DB_PORT}")
    logger.info(f"  Database:         {database_config.DB_NAME}")
    logger.info("=" * 70)
    
    # Initialize database with migrations
    logger.info("")
    logger.info(">> Database Initialization...")
    try:
        init_db()
        logger.info("   OK - Database ready")
    except Exception as e:
        logger.error(f"   FAILED - Database initialization failed: {e}")
        logger.error("   Cannot proceed without database. Exiting.")
        raise
    
    # Seed initial data (idempotent - safe to call multiple times)
    logger.info("")
    logger.info(">> Seeding Initial Data...")
    try:
        from src.core.seed_data import run_all_seeds
        db = SessionLocal()
        seed_results = run_all_seeds(db)
        db.close()
        logger.info(f"   OK - Seeding completed: {seed_results}")
    except Exception as e:
        logger.warning(f"   SKIPPED - Seeding failed (non-critical): {e}")
    
    # Uvicorn requires an import string when reload is enabled.
    # IMPORTANT: Reload is DISABLED by default to prevent data loss from dropping tables
    # on every file change. Set ENABLE_RELOAD=true environment variable to enable.
    enable_reload = os.getenv("ENABLE_RELOAD", "false").lower() == "true"
    app_target = "src.api.routes:app" if enable_reload else app

    logger.info("")
    logger.info(">> Starting HTTP Server...")
    logger.info(f"   LISTENING on http://{server_config.SERVER_HOST}:{server_config.SERVER_PORT}")
    logger.info("=" * 70)
    logger.info("")
    
    # Start server
    uvicorn.run(
        app_target,
        host=server_config.SERVER_HOST,
        port=server_config.SERVER_PORT,
        log_level=app_config.LOG_LEVEL.lower(),
        reload=enable_reload,
        access_log=True
    )


if __name__ == "__main__":
    main()
