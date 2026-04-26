"""
Dynamic Service Discovery Registry — SQLite backed.

How it works
────────────
• All nodes share a single SQLite file: data/registry.db
• On startup every node writes itself into the `registry` table with a
  `last_seen` timestamp.
• A background asyncio task (DiscoveryWorker) refreshes the row every
  DISCOVERY_INTERVAL seconds and reads back all rows whose last_seen is
  within PEER_TTL_SECONDS.  Stale rows are automatically ignored.
• When the peer list changes the worker calls back into GossipNode and
  ConsistentHash to add/remove nodes without any restart.

No Redis, no Consul, no Docker — just a file on disk.
"""
import asyncio
import sqlite3
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


# ── Low-level registry table ──────────────────────────────────────────────────

REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS registry (
    server_id  TEXT PRIMARY KEY,
    host       TEXT NOT NULL,
    port       INTEGER NOT NULL,
    last_seen  REAL NOT NULL       -- Unix timestamp (float)
);
"""


class ServiceRegistry:
    """
    Thin wrapper around a shared SQLite file.
    All operations are synchronous (called from threads / asyncio.to_thread).
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_schema()

    # ── internal ─────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_schema(self):
        with self._conn() as conn:
            conn.execute(REGISTRY_SCHEMA)
            conn.commit()

    # ── public API ────────────────────────────────────────────────────────────

    def register(self, server_id: str, host: str, port: int) -> None:
        """Upsert this server's registration (call periodically to stay alive)."""
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO registry (server_id, host, port, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(server_id) DO UPDATE SET
                    host      = excluded.host,
                    port      = excluded.port,
                    last_seen = excluded.last_seen
                """,
                (server_id, host, port, now),
            )
            conn.commit()

    def deregister(self, server_id: str) -> None:
        """Remove this server from the registry (clean shutdown)."""
        with self._conn() as conn:
            conn.execute("DELETE FROM registry WHERE server_id = ?", (server_id,))
            conn.commit()

    def get_active_peers(
        self,
        current_server_id: str,
        ttl_seconds: int = 15,
    ) -> List[Dict]:
        """
        Return all servers (excluding self) that have checked in within ttl_seconds.
        """
        cutoff = time.time() - ttl_seconds
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT server_id, host, port, last_seen
                FROM   registry
                WHERE  last_seen >= ?
                  AND  server_id  != ?
                ORDER  BY server_id
                """,
                (cutoff, current_server_id),
            ).fetchall()

        return [
            {
                "server_id": r[0],
                "host":      r[1],
                "port":      r[2],
                "last_seen": datetime.utcfromtimestamp(r[3]).isoformat(),
            }
            for r in rows
        ]

    def get_all_active(self, ttl_seconds: int = 15) -> List[Dict]:
        """Return ALL active servers including self."""
        cutoff = time.time() - ttl_seconds
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
                "host":      r[1],
                "port":      r[2],
                "last_seen": datetime.utcfromtimestamp(r[3]).isoformat(),
            }
            for r in rows
        ]


# ── Background worker ─────────────────────────────────────────────────────────

class DiscoveryWorker:
    """
    Asyncio background task that:
      1. Renews this server's registration in the shared registry.
      2. Detects new or disappeared peers and calls back to update
         GossipNode and ConsistentHash (hash_ring) dynamically.
    """

    def __init__(
        self,
        registry: ServiceRegistry,
        server_id: str,
        host: str,
        port: int,
        interval_sec: int = 5,
        ttl_seconds:  int = 15,
        on_peer_added:   Optional[Callable[[str, str, int], None]] = None,
        on_peer_removed: Optional[Callable[[str], None]] = None,
    ):
        self.registry     = registry
        self.server_id    = server_id
        self.host         = host
        self.port         = port
        self.interval_sec = interval_sec
        self.ttl_seconds  = ttl_seconds
        self.on_peer_added   = on_peer_added    # callback(server_id, host, port)
        self.on_peer_removed = on_peer_removed  # callback(server_id)

        self._known_peers: Dict[str, Dict] = {}   # server_id -> {host, port}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the discovery background loop."""
        # Register immediately so peers can find us right away
        await asyncio.to_thread(
            self.registry.register, self.server_id, self.host, self.port
        )
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.debug(
            f"[Discovery] Worker started — refreshing every {self.interval_sec}s "
            f"(peer TTL={self.ttl_seconds}s)"
        )

    async def stop(self):
        """Stop the worker and deregister from the cluster."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(self.registry.deregister, self.server_id)
        logger.debug("[Discovery] Worker stopped — deregistered from cluster")

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as exc:
                logger.error(f"[Discovery] Error in discovery loop: {exc}", exc_info=True)
            await asyncio.sleep(self.interval_sec)

    async def _tick(self):
        # 1. Renew our own registration
        await asyncio.to_thread(
            self.registry.register, self.server_id, self.host, self.port
        )

        # 2. Fetch current active peers
        active = await asyncio.to_thread(
            self.registry.get_active_peers, self.server_id, self.ttl_seconds
        )
        active_map: Dict[str, Dict] = {p["server_id"]: p for p in active}

        # 3. Detect newly joined peers
        for sid, info in active_map.items():
            if sid not in self._known_peers:
                logger.info(f"[Discovery] ✚ New peer joined cluster: {sid} @ {info['host']}:{info['port']}")
                if self.on_peer_added:
                    self.on_peer_added(sid, info["host"], info["port"])
                self._known_peers[sid] = info

        # 4. Detect departed peers
        gone = set(self._known_peers) - set(active_map)
        for sid in gone:
            logger.warning(f"[Discovery] ✖ Peer left cluster (TTL expired): {sid}")
            if self.on_peer_removed:
                self.on_peer_removed(sid)
            del self._known_peers[sid]

    @property
    def known_peers(self) -> Dict[str, Dict]:
        """Current snapshot of known peers."""
        return dict(self._known_peers)
