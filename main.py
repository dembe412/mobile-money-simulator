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
from src.api.routes import app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/server.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Start the server"""
    logger.info("=" * 70)
    logger.info(f"Starting {app_config.APP_NAME} v{app_config.APP_VERSION}")
    logger.info("=" * 70)
    logger.info(f"Server ID: {server_config.SERVER_ID}")
    logger.info(f"Server Name: {server_config.SERVER_NAME}")
    logger.info(f"Server Address: {server_config.SERVER_HOST}:{server_config.SERVER_PORT}")
    logger.info(f"Database: {database_config.DB_HOST}:{database_config.DB_PORT}")
    logger.info(f"Environment: {app_config.APP_ENV}")
    logger.info("=" * 70 + "\n")
    
    # Initialize database
    logger.info("Initializing database...")
    init_db()
    
    # Seed initial data (idempotent - safe to call multiple times)
    logger.info("Seeding initial data...")
    try:
        from src.core.seed_data import run_all_seeds
        db = SessionLocal()
        seed_results = run_all_seeds(db)
        db.close()
        logger.info(f"Seeding results: {seed_results}")
    except Exception as e:
        logger.warning(f"Seeding skipped or failed (non-critical): {e}")
    
    # Uvicorn requires an import string when reload is enabled.
    # IMPORTANT: Reload is DISABLED by default to prevent data loss from dropping tables
    # on every file change. Set ENABLE_RELOAD=true environment variable to enable.
    enable_reload = os.getenv("ENABLE_RELOAD", "false").lower() == "true"
    app_target = "src.api.routes:app" if enable_reload else app

    # Start server
    uvicorn.run(
        app_target,
        host=server_config.SERVER_HOST,
        port=server_config.SERVER_PORT,
        log_level=app_config.LOG_LEVEL.lower(),
        reload=enable_reload
    )


if __name__ == "__main__":
    main()
