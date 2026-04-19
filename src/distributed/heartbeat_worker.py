"""
Background worker for gossip protocol heartbeats
Periodically pings peers to maintain cluster health information
"""
import asyncio
import httpx
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from src.distributed.gossip import GossipNode
from config.settings import server_config

logger = logging.getLogger(__name__)


class HeartbeatWorker:
    """
    Background worker that periodically sends heartbeats to peer servers
    Maintains cluster membership and health information
    """
    
    def __init__(
        self,
        gossip_node: GossipNode,
        db_session_factory,
        interval_sec: int = 5,
        timeout_sec: int = 3,
    ):
        """
        Initialize heartbeat worker
        
        Args:
            gossip_node: GossipNode instance to manage
            db_session_factory: SessionLocal factory for database access
            interval_sec: How often to send heartbeats (seconds)
            timeout_sec: HTTP request timeout (seconds)
        """
        self.gossip_node = gossip_node
        self.db_session_factory = db_session_factory
        self.interval_sec = interval_sec
        self.timeout_sec = timeout_sec
        self.running = False
        self.task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the heartbeat worker"""
        self.running = True
        self.task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"[OK] Heartbeat worker started (interval={self.interval_sec}s, timeout={self.timeout_sec}s)")
    
    async def stop(self):
        """Stop the heartbeat worker"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("[OK] Heartbeat worker stopped")
    
    async def _heartbeat_loop(self):
        """Main loop that sends heartbeats periodically"""
        while self.running:
            try:
                await self._send_heartbeats()
                await self._update_server_status()
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}", exc_info=True)
            
            # Wait before next heartbeat
            await asyncio.sleep(self.interval_sec)
    
    async def _send_heartbeats(self):
        """Send heartbeat to all known peers"""
        peers = self.gossip_node.get_all_peers()
        
        if not peers:
            logger.debug("No peers to heartbeat")
            return
        
        # Create heartbeat message
        heartbeat_msg = self.gossip_node.create_heartbeat_message(peer_list=peers)
        msg_dict = heartbeat_msg.to_dict()
        
        logger.debug(f"Sending heartbeat to {len(peers)} peer(s)")
        
        # Send to each peer (non-blocking, parallel)
        tasks = [
            self._send_heartbeat_to_peer(peer.server_id, peer.host, peer.port, msg_dict)
            for peer in peers
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successes/failures
        successes = sum(1 for r in results if r is True)
        failures = len(results) - successes
        
        if failures > 0:
            logger.warning(f"Heartbeat cycle: {successes} sent, {failures} FAILED out of {len(peers)} peers")
        else:
            logger.debug(f"Heartbeat cycle: All {len(peers)} peers reachable [OK]")
    
    async def _send_heartbeat_to_peer(
        self,
        peer_id: str,
        host: str,
        port: int,
        message: dict
    ) -> bool:
        """
        Send heartbeat to a single peer
        
        Args:
            peer_id: Peer server ID
            host: Peer hostname
            port: Peer port
            message: Gossip message to send
            
        Returns:
            True if successful, False otherwise
        """
        url = f"http://{host}:{port}/api/v1/gossip/heartbeat"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.post(url, json=message)
                
                if response.status_code == 200:
                    # Heartbeat successful
                    self.gossip_node.peers[peer_id].last_contact = datetime.utcnow()
                    self.gossip_node.peers[peer_id].status = "online"
                    self.gossip_node.peers[peer_id].error_count = 0
                    logger.debug(f"  {peer_id}: heartbeat OK (200)")
                    return True
                else:
                    logger.warning(f"  {peer_id}: heartbeat failed ({response.status_code})")
                    self._handle_peer_error(peer_id)
                    return False
        
        except asyncio.TimeoutError:
            logger.warning(f"  {peer_id}: heartbeat TIMEOUT after {self.timeout_sec}s")
            self._handle_peer_error(peer_id)
            return False
        
        except Exception as e:
            logger.warning(f"  {peer_id}: heartbeat ERROR: {type(e).__name__}: {str(e)[:80]}")
            self._handle_peer_error(peer_id)
            return False
    
    def _handle_peer_error(self, peer_id: str):
        """Handle failed heartbeat to peer"""
        peer = self.gossip_node.peers.get(peer_id)
        if peer:
            peer.error_count = peer.error_count + 1
            
            # Mark as offline after 3 consecutive failures
            if peer.error_count >= 3:
                peer.status = "offline"
                logger.warning(f"[WARN] Peer {peer_id} marked OFFLINE (consecutive failures: {peer.error_count})")
            else:
                logger.debug(f"  Peer {peer_id} error count: {peer.error_count}/3")
    
    async def _update_server_status(self):
        """Update ServerStatus table with current gossip state"""
        try:
            from src.models import ServerStatus
            
            db = self.db_session_factory()
            try:
                # Get or create server status entry
                status = db.query(ServerStatus).filter(
                    ServerStatus.server_id == self.gossip_node.server_id
                ).first()
                
                if not status:
                    status = ServerStatus(
                        server_id=self.gossip_node.server_id,
                        server_name=server_config.SERVER_NAME,
                        host=self.gossip_node.host,
                        port=self.gossip_node.port,
                        status="online",
                    )
                    db.add(status)
                    logger.info(f"[NEW] ServerStatus entry created for {self.gossip_node.server_id}")
                
                # Update status
                status.status = "online"
                status.last_heartbeat = datetime.utcnow()
                status.peer_vector_clock = self.gossip_node.get_vector_clock()
                
                # Calculate max sync lag across all peers
                max_lag = 0
                healthy_peers = self.gossip_node.get_healthy_peers()
                for peer in healthy_peers:
                    if peer.last_contact:
                        lag = (datetime.utcnow() - peer.last_contact).total_seconds()
                        max_lag = max(max_lag, lag)
                
                status.sync_lag_seconds = int(max_lag)
                status.pending_events_count = len(self.gossip_node.pending_event_ids)
                
                db.commit()
                
                # Log status update summary
                healthy_count = len(healthy_peers)
                total_peers = len(self.gossip_node.get_all_peers())
                logger.debug(
                    f"[STATUS] {healthy_count}/{total_peers} peers healthy, "
                    f"lag={max_lag:.1f}s, pending_events={status.pending_events_count}"
                )
            
            finally:
                db.close()
        
        except Exception as e:
            logger.error(f"Error updating ServerStatus: {e}", exc_info=True)


async def run_heartbeat_worker(gossip_node: GossipNode, db_session_factory):
    """
    Start and run heartbeat worker (can be awaited in main)
    
    Args:
        gossip_node: GossipNode instance
        db_session_factory: SessionLocal factory
    """
    worker = HeartbeatWorker(gossip_node, db_session_factory)
    await worker.start()
    return worker
