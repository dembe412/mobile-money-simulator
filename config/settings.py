"""
Configuration management for Mobile Money System
"""
from pydantic_settings import BaseSettings
from typing import List, Dict, Optional
import os


class ServerConfig(BaseSettings):
    """Server identification and configuration"""
    SERVER_ID: str = os.getenv("SERVER_ID", "server_1")
    SERVER_NAME: str = os.getenv("SERVER_NAME", "Primary Server")
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8001"))
    
    class Config:
        env_file = ".env"


class DatabaseConfig(BaseSettings):
    """PostgreSQL configuration"""
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "postgres")
    DB_NAME: str = os.getenv("DB_NAME", "mobile_money_system")
    
    @property
    def DATABASE_URL(self) -> str:
        # Use psycopg (v3) driver for better compatibility with newer Python versions.
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    ECHO_SQL: bool = os.getenv("ECHO_SQL", "false").lower() == "true"
    
    class Config:
        env_file = ".env"


class RedisConfig(BaseSettings):
    """Redis configuration"""
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    
    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    class Config:
        env_file = ".env"


class OperationConfig(BaseSettings):
    """Operation behavior configuration"""
    LOCK_TIMEOUT: int = int(os.getenv("LOCK_TIMEOUT", "30"))
    TRANSACTION_TIMEOUT: int = int(os.getenv("TRANSACTION_TIMEOUT", "60"))
    OPERATION_RETRY_COUNT: int = int(os.getenv("OPERATION_RETRY_COUNT", "3"))
    OPERATION_RETRY_DELAY: int = int(os.getenv("OPERATION_RETRY_DELAY", "1000"))
    
    class Config:
        env_file = ".env"


class ReplicationConfig(BaseSettings):
    """Replication and peer configuration (P2P Distributed)"""
    REPLICATION_ENABLED: bool = os.getenv("REPLICATION_ENABLED", "true").lower() == "true"
    REPLICATION_INTERVAL: int = int(os.getenv("REPLICATION_INTERVAL", "5"))
    REPLICATION_TIMEOUT: int = int(os.getenv("REPLICATION_TIMEOUT", "10"))
    REPLICATION_RETRY_COUNT: int = int(os.getenv("REPLICATION_RETRY_COUNT", "3"))
    HEARTBEAT_INTERVAL: int = int(os.getenv("HEARTBEAT_INTERVAL", "10"))
    SYNC_INTERVAL: int = int(os.getenv("SYNC_INTERVAL", "5"))
    HASH_VIRTUAL_NODES: int = int(os.getenv("HASH_VIRTUAL_NODES", "150"))
    HASH_ALGORITHM: str = os.getenv("HASH_ALGORITHM", "crc32")
    
    @property
    def PEER_SERVERS(self) -> List[str]:
        """Get peer server URLs from environment"""
        peers_env = os.getenv("PEER_SERVERS", "")
        if peers_env:
            # Parse comma-separated list: http://192.168.1.11:8002,http://192.168.1.12:8003
            return [peer.strip() for peer in peers_env.split(",") if peer.strip()]
        # Default fallback
        return [
            "http://localhost:8002",
            "http://localhost:8003",
        ]
    
    class Config:
        env_file = ".env"


class SecurityConfig(BaseSettings):
    """Security configuration"""
    REQUEST_SIGNING_KEY: str = os.getenv("REQUEST_SIGNING_KEY", "your-secret-key-change-in-production")
    API_TOKEN_EXPIRY: int = int(os.getenv("API_TOKEN_EXPIRY", "3600"))
    MAX_REQUEST_SIZE: int = int(os.getenv("MAX_REQUEST_SIZE", "10485760"))
    
    class Config:
        env_file = ".env"


class USSDConfig(BaseSettings):
    """USSD protocol configuration"""
    USSD_SESSION_TIMEOUT: int = int(os.getenv("USSD_SESSION_TIMEOUT", "180"))
    USSD_REQUEST_TIMEOUT: int = int(os.getenv("USSD_REQUEST_TIMEOUT", "60"))
    
    class Config:
        env_file = ".env"


class NotificationConfig(BaseSettings):
    """Notification system configuration"""
    ASYNC_NOTIFICATION_ENABLED: bool = os.getenv("ASYNC_NOTIFICATION_ENABLED", "true").lower() == "true"
    RETRY_FAILED_NOTIFICATIONS: bool = os.getenv("RETRY_FAILED_NOTIFICATIONS", "true").lower() == "true"
    NOTIFICATION_RETRY_MAX: int = int(os.getenv("NOTIFICATION_RETRY_MAX", "3"))
    NOTIFICATION_BATCH_SIZE: int = int(os.getenv("NOTIFICATION_BATCH_SIZE", "100"))
    
    # Mock SMS gateway (replace with real service)
    SMS_GATEWAY_URL: Optional[str] = os.getenv("SMS_GATEWAY_URL", None)
    SMS_GATEWAY_API_KEY: Optional[str] = os.getenv("SMS_GATEWAY_API_KEY", None)
    
    class Config:
        env_file = ".env"


class AppConfig(BaseSettings):
    """Application-level configuration"""
    APP_NAME: str = "Mobile Money System"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_DEBUG: bool = os.getenv("APP_ENV", "development") == "development"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    TIMEZONE: str = os.getenv("TIMEZONE", "Africa/Nairobi")
    
    class Config:
        env_file = ".env"


# Create singleton instances
server_config = ServerConfig()
database_config = DatabaseConfig()
redis_config = RedisConfig()
operation_config = OperationConfig()
replication_config = ReplicationConfig()
security_config = SecurityConfig()
ussd_config = USSDConfig()
notification_config = NotificationConfig()
app_config = AppConfig()
