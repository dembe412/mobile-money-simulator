"""
Configuration management for Mobile Money System
All settings can be overridden via environment variables.
No Docker, no Redis, no PostgreSQL required — uses SQLite by default.
"""
import os
from pathlib import Path

# ── Project root (parent of config/)
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


# ── Server identity ──────────────────────────────────────────────────────────
class ServerConfig:
    """Server identification and networking config"""
    SERVER_ID:   str = os.getenv("SERVER_ID",   "server_1")
    SERVER_NAME: str = os.getenv("SERVER_NAME", "Server 1")
    SERVER_HOST: str = os.getenv("SERVER_HOST", "127.0.0.1")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8001"))


# ── Database ─────────────────────────────────────────────────────────────────
class DatabaseConfig:
    """
    SQLite database configuration.
    Each node gets its own isolated database file:
        data/server_1.db   (for SERVER_ID=server_1)
        data/server_2.db   (for SERVER_ID=server_2)
        …

    The service-discovery registry is shared:
        data/registry.db
    """

    @property
    def DB_PATH(self) -> Path:
        """Absolute path to this server's SQLite database file"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        server_id = os.getenv("SERVER_ID", "server_1")
        return DATA_DIR / f"{server_id}.db"

    @property
    def DATABASE_URL(self) -> str:
        """SQLAlchemy connection string for this server"""
        return f"sqlite:///{self.DB_PATH}"

    @property
    def REGISTRY_DB_PATH(self) -> Path:
        """Shared SQLite file used for service-discovery"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DATA_DIR / "registry.db"

    ECHO_SQL: bool = os.getenv("ECHO_SQL", "false").lower() == "true"

    # Legacy attributes kept for compatibility (unused with SQLite)
    DB_HOST:     str = os.getenv("DB_HOST",     "localhost")
    DB_PORT:     int = int(os.getenv("DB_PORT",  "5432"))
    DB_USER:     str = os.getenv("DB_USER",     "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "postgres")
    DB_NAME:     str = os.getenv("DB_NAME",     "mobile_money_system")


# ── Operation behaviour ───────────────────────────────────────────────────────
class OperationConfig:
    LOCK_TIMEOUT:        int = int(os.getenv("LOCK_TIMEOUT",        "30"))
    TRANSACTION_TIMEOUT: int = int(os.getenv("TRANSACTION_TIMEOUT", "60"))
    OPERATION_RETRY_COUNT: int = int(os.getenv("OPERATION_RETRY_COUNT", "3"))
    OPERATION_RETRY_DELAY: int = int(os.getenv("OPERATION_RETRY_DELAY", "1000"))


# ── Replication / gossip ──────────────────────────────────────────────────────
class ReplicationConfig:
    REPLICATION_ENABLED:  bool = os.getenv("REPLICATION_ENABLED", "true").lower() == "true"
    REPLICATION_INTERVAL: int  = int(os.getenv("REPLICATION_INTERVAL", "2"))
    REPLICATION_TIMEOUT:  int  = int(os.getenv("REPLICATION_TIMEOUT",  "5"))
    HEARTBEAT_INTERVAL:   int  = int(os.getenv("HEARTBEAT_INTERVAL",   "5"))
    DISCOVERY_INTERVAL:   int  = int(os.getenv("DISCOVERY_INTERVAL",   "5"))   # peer refresh
    PEER_TTL_SECONDS:     int  = int(os.getenv("PEER_TTL_SECONDS",     "15"))  # stale threshold
    HASH_VIRTUAL_NODES:   int  = int(os.getenv("HASH_VIRTUAL_NODES",   "150"))
    HASH_STRATEGY:        str  = os.getenv("HASH_STRATEGY", "consistent")


# ── Security ──────────────────────────────────────────────────────────────────
class SecurityConfig:
    REQUEST_SIGNING_KEY: str = os.getenv("REQUEST_SIGNING_KEY", "change-me-in-production")
    API_TOKEN_EXPIRY:    int = int(os.getenv("API_TOKEN_EXPIRY", "3600"))


# ── USSD ──────────────────────────────────────────────────────────────────────
class USSDConfig:
    USSD_SESSION_TIMEOUT: int = int(os.getenv("USSD_SESSION_TIMEOUT", "180"))
    USSD_REQUEST_TIMEOUT: int = int(os.getenv("USSD_REQUEST_TIMEOUT", "60"))


# ── Application ───────────────────────────────────────────────────────────────
class AppConfig:
    APP_NAME:    str  = "Mobile Money System"
    APP_VERSION: str  = "2.0.0"
    APP_ENV:     str  = os.getenv("APP_ENV", "development")
    APP_DEBUG:   bool = os.getenv("APP_ENV", "development") == "development"
    LOG_LEVEL:   str  = os.getenv("LOG_LEVEL", "INFO")
    TIMEZONE:    str  = os.getenv("TIMEZONE", "Africa/Nairobi")


# ── Singleton instances ───────────────────────────────────────────────────────
server_config      = ServerConfig()
database_config    = DatabaseConfig()
operation_config   = OperationConfig()
replication_config = ReplicationConfig()
security_config    = SecurityConfig()
ussd_config        = USSDConfig()
app_config         = AppConfig()
