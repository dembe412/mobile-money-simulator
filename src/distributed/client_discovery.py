"""
Client-side Service Discovery
Enables clients to automatically discover and connect to available servers
without hardcoded URLs.
"""
import sqlite3
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ClientDiscoveryError(Exception):
    """Raised when service discovery fails"""
    pass


class ClientServiceDiscovery:
    """
    Client-side service discovery mechanism.
    Queries the shared registry database to find active servers.
    """

    def __init__(self, registry_db_path: Path, peer_ttl_seconds: int = 15):
        """
        Initialize client discovery
        
        Args:
            registry_db_path: Path to the shared registry.db file
            peer_ttl_seconds: How old a server registration can be before considering it stale
        """
        self.registry_db_path = registry_db_path
        self.peer_ttl_seconds = peer_ttl_seconds
        self._validate_registry()

    def _validate_registry(self):
        """Ensure the registry database exists and has the correct schema"""
        if not self.registry_db_path.exists():
            raise ClientDiscoveryError(
                f"Registry database not found at {self.registry_db_path}. "
                "Please ensure at least one server is running to initialize the registry."
            )

    def _conn(self) -> sqlite3.Connection:
        """Create a database connection"""
        conn = sqlite3.connect(str(self.registry_db_path), timeout=10, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def discover(self) -> List[str]:
        """
        Discover all active servers and return their URLs
        
        Returns:
            List of server URLs (e.g., ['http://127.0.0.1:8001', ...])
            
        Raises:
            ClientDiscoveryError: If no active servers are found
        """
        try:
            servers = self.get_active_servers()
            
            if not servers:
                raise ClientDiscoveryError(
                    "No active servers found in the registry. "
                    "Please ensure at least one server is running."
                )
            
            urls = [f"http://{s['host']}:{s['port']}" for s in servers]
            logger.info(f"Discovered {len(urls)} active server(s): {urls}")
            return urls
            
        except sqlite3.OperationalError as e:
            raise ClientDiscoveryError(f"Failed to query registry: {e}")

    def get_active_servers(self, ttl_seconds: Optional[int] = None) -> List[Dict]:
        """
        Get all active servers from the registry
        
        Args:
            ttl_seconds: Override default TTL for this query
            
        Returns:
            List of server info dicts with keys: server_id, host, port, last_seen
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.peer_ttl_seconds
        cutoff = time.time() - ttl
        
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    """
                    SELECT server_id, host, port, last_seen
                    FROM   registry
                    WHERE  last_seen >= ?
                    ORDER  BY server_id
                    """,
                    (cutoff,),
                ).fetchall()
            
            return [
                {
                    "server_id": r[0],
                    "host": r[1],
                    "port": r[2],
                    "last_seen": datetime.utcfromtimestamp(r[3]).isoformat(),
                }
                for r in rows
            ]
        except sqlite3.OperationalError as e:
            logger.error(f"Failed to query active servers: {e}")
            return []

    def wait_for_servers(
        self,
        min_servers: int = 1,
        max_wait_seconds: int = 30,
        poll_interval: float = 1.0,
    ) -> List[str]:
        """
        Wait for at least min_servers to become available
        Useful during system startup
        
        Args:
            min_servers: Minimum number of servers to wait for
            max_wait_seconds: Maximum time to wait
            poll_interval: How often to check (in seconds)
            
        Returns:
            List of discovered server URLs
            
        Raises:
            ClientDiscoveryError: If min_servers not reached within max_wait_seconds
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait_seconds:
            servers = self.get_active_servers()
            
            if len(servers) >= min_servers:
                urls = [f"http://{s['host']}:{s['port']}" for s in servers]
                logger.info(
                    f"Service discovery: Found {len(urls)} server(s) after "
                    f"{time.time() - start_time:.1f}s"
                )
                return urls
            
            logger.debug(
                f"Waiting for servers... ({len(servers)}/{min_servers}) "
                f"after {time.time() - start_time:.1f}s"
            )
            time.sleep(poll_interval)
        
        # Timeout reached
        servers = self.get_active_servers()
        raise ClientDiscoveryError(
            f"Service discovery timeout: Only found {len(servers)} server(s), "
            f"needed {min_servers}. Waited {max_wait_seconds}s."
        )

    def get_server_info(self, server_id: str) -> Optional[Dict]:
        """Get info about a specific server"""
        try:
            with self._conn() as conn:
                row = conn.execute(
                    """
                    SELECT server_id, host, port, last_seen
                    FROM   registry
                    WHERE  server_id = ?
                    """,
                    (server_id,),
                ).fetchone()
            
            if row:
                return {
                    "server_id": row[0],
                    "host": row[1],
                    "port": row[2],
                    "last_seen": datetime.utcfromtimestamp(row[3]).isoformat(),
                }
            return None
        except sqlite3.OperationalError:
            return None

    def is_healthy(self) -> bool:
        """Check if at least one server is available"""
        try:
            servers = self.get_active_servers()
            return len(servers) > 0
        except Exception:
            return False
