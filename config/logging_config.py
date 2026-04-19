"""
Enhanced logging configuration for clarity on distributed system operations
"""
import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime


class ServerContextFilter(logging.Filter):
    """Add server context to all log records"""
    
    def __init__(self, server_id: str, server_port: int):
        super().__init__()
        self.server_id = server_id
        self.server_port = server_port
    
    def filter(self, record):
        record.server_id = self.server_id
        record.server_port = self.server_port
        return True


def setup_logging(server_id: str, server_port: int, log_level: str = "INFO"):
    """
    Configure logging with server-specific output.
    
    Creates:
    1. Server-specific log file: logs/server_{server_id}.log
    2. Console output with server context
    3. Structured logging for easy parsing
    
    Args:
        server_id: Unique server identifier (e.g., 'server_1')
        server_port: Server port number
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    # Ensure logs directory exists
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Remove existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Set root logger level
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Create server context filter
    context_filter = ServerContextFilter(server_id, server_port)
    
    # Detailed format with server context (ASCII-safe for Windows)
    detailed_format = (
        '%(asctime)s - [%(server_id)s:%(server_port)d] - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Short format for console (more readable, ASCII-safe)
    console_format = (
        '[%(server_id)s] %(levelname)-8s | %(name)s: %(message)s'
    )
    
    # 1. Server-specific file handler
    server_log_file = log_dir / f"server_{server_id}.log"
    file_handler = logging.FileHandler(str(server_log_file), encoding='utf-8')
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    file_handler.setFormatter(logging.Formatter(detailed_format))
    file_handler.addFilter(context_filter)
    root_logger.addHandler(file_handler)
    
    # 2. Combined log file for all servers
    combined_log_file = log_dir / "server.log"
    combined_handler = logging.FileHandler(str(combined_log_file), encoding='utf-8')
    combined_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    combined_handler.setFormatter(logging.Formatter(detailed_format))
    combined_handler.addFilter(context_filter)
    root_logger.addHandler(combined_handler)
    
    # 3. Console handler with proper encoding
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter(console_format))
    console_handler.addFilter(context_filter)
    root_logger.addHandler(console_handler)
    
    # Get main logger
    logger = logging.getLogger(__name__)
    
    # Log initialization
    logger.info("=" * 70)
    logger.info(f"Logging initialized for {server_id}:{server_port}")
    logger.info(f"Log level: {log_level}")
    logger.info(f"Server-specific log: {server_log_file}")
    logger.info(f"Combined log: {combined_log_file}")
    logger.info("=" * 70)
    
    return logger


def get_module_logger(module_name: str) -> logging.Logger:
    """Get a logger for a specific module"""
    return logging.getLogger(module_name)
