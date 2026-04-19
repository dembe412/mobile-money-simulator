"""
Gossip protocol configuration
"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Dict, Optional
import os


class GossipConfig(BaseSettings):
    """Gossip protocol configuration"""
    
    # Heartbeat settings
    HEARTBEAT_INTERVAL_SEC: int = int(os.getenv("HEARTBEAT_INTERVAL_SEC", "5"))
    HEARTBEAT_TIMEOUT_SEC: int = int(os.getenv("HEARTBEAT_TIMEOUT_SEC", "10"))
    HEARTBEAT_MAX_RETRIES: int = int(os.getenv("HEARTBEAT_MAX_RETRIES", "3"))
    
    # Replication settings
    REPLICATION_BATCH_SIZE: int = int(os.getenv("REPLICATION_BATCH_SIZE", "10"))
    REPLICATION_BATCH_INTERVAL_SEC: int = int(os.getenv("REPLICATION_BATCH_INTERVAL_SEC", "2"))
    REPLICATION_TIMEOUT_SEC: int = int(os.getenv("REPLICATION_TIMEOUT_SEC", "5"))
    REPLICATION_ENABLED: bool = os.getenv("REPLICATION_ENABLED", "true").lower() == "true"
    
    # Quorum settings
    QUORUM_SIZE: int = int(os.getenv("QUORUM_SIZE", "2"))  # 2/3 majority
    QUORUM_TIMEOUT_SEC: int = int(os.getenv("QUORUM_TIMEOUT_SEC", "5"))
    QUORUM_REQUIRED_FOR: list = []  # Operations requiring quorum: ['transfer', 'large_withdrawal']
    
    # Vector clock settings
    VECTOR_CLOCK_ENABLED: bool = os.getenv("VECTOR_CLOCK_ENABLED", "true").lower() == "true"
    
    # Conflict resolution
    CONFLICT_RESOLUTION_STRATEGY: str = os.getenv("CONFLICT_RESOLUTION_STRATEGY", "last_write_wins")
    
    # Consistency modes
    CONSISTENCY_LEVEL: str = os.getenv("CONSISTENCY_LEVEL", "eventual")  # eventual or strong
    DEFAULT_READ_CONSISTENCY: str = os.getenv("DEFAULT_READ_CONSISTENCY", "eventual")
    
    model_config = ConfigDict(env_file=".env", extra="ignore")


gossip_config = GossipConfig()
