"""
Main application entry point
Starts the Mobile Money Server
"""
import uvicorn
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import server_config, app_config, database_config
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
    logger.info(f"Database: {database_config.DB_HOST}:{database_config.DB_PORT}/{database_config.DB_NAME}")
    logger.info(f"Environment: {app_config.APP_ENV}")
    logger.info("=" * 70 + "\n")
    
    # Uvicorn requires an import string when reload is enabled.
    app_target = "src.api.routes:app" if app_config.APP_DEBUG else app

    # Start server
    uvicorn.run(
        app_target,
        host=server_config.SERVER_HOST,
        port=server_config.SERVER_PORT,
        log_level=app_config.LOG_LEVEL.lower(),
        reload=app_config.APP_DEBUG
    )


if __name__ == "__main__":
    main()
