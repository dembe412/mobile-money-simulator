"""
Replication Manager for synchronizing events across peers
Handles event broadcasting, acknowledgement collection, and conflict detection
"""
import asyncio
import httpx
import logging
from datetime import datetime
from typing import List, Dict, Optional
from decimal import Decimal

from src.core.events import Event
from src.distributed.gossip import GossipNode
from src.distributed.vector_clock import VectorClock, detect_concurrent_operations

logger = logging.getLogger(__name__)


class ReplicationManager:
    """
    Orchestrates replication of events across the distributed system
    
    Responsibilities:
    1. Broadcast events to peers
    2. Collect acknowledgements
    3. Detect conflicts (concurrent operations)
    4. Update replication status
    """
    
    def __init__(
        self,
        gossip_node: GossipNode,
        server_id: str,
        db_session_factory,
        batch_size: int = 10,
        batch_interval_sec: int = 2,
        replicate_timeout_sec: int = 5,
    ):
        """
        Initialize replication manager
        
        Args:
            gossip_node: GossipNode instance for peer management
            server_id: This server's ID
            db_session_factory: SessionLocal factory for database access
            batch_size: Number of events to batch before replicating
            batch_interval_sec: How often to flush batch
            replicate_timeout_sec: Timeout for replication requests
        """
        self.gossip_node = gossip_node
        self.server_id = server_id
        self.db_session_factory = db_session_factory
        self.batch_size = batch_size
        self.batch_interval_sec = batch_interval_sec
        self.replicate_timeout_sec = replicate_timeout_sec
        
        # Replication state
        self.pending_replication: List[Event] = []  # Events waiting to be replicated
        self.conflict_log: Dict[str, Dict] = {}  # Track detected conflicts
        
        self.running = False
        self.task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the replication manager"""
        self.running = True
        self.task = asyncio.create_task(self._replication_loop())
        logger.info(f"Replication manager started (batch_size={self.batch_size}, interval={self.batch_interval_sec}s)")
    
    async def stop(self):
        """Stop the replication manager"""
        self.running = False
        
        # Flush any pending events
        if self.pending_replication:
            await self._replicate_batch(self.pending_replication)
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("Replication manager stopped")
    
    async def _replication_loop(self):
        """Main loop that batches and replicates events"""
        while self.running:
            try:
                if self.pending_replication:
                    # Replicate all pending events up to batch_size
                    to_replicate = self.pending_replication[:self.batch_size]
                    self.pending_replication = self.pending_replication[self.batch_size:]
                    await self._replicate_batch(to_replicate)
            
            except Exception as e:
                logger.error(f"Error in replication loop: {e}", exc_info=True)
            
            # Wait before next iteration
            await asyncio.sleep(self.batch_interval_sec)
    
    def queue_event_for_replication(self, event: Event):
        """
        Queue an event for replication to peers
        
        Args:
            event: Event to replicate
        """
        self.pending_replication.append(event)
        self.gossip_node.queue_event_for_replication(event.event_id)
        logger.debug(f"Event queued for replication: {event.event_id}")
    
    async def _replicate_batch(self, batch: List[Event]):
        """
        Replicate a batch of events to peers
        
        Args:
            batch: List of events to replicate
        """
        if not batch:
            return
        
        peers = self.gossip_node.get_healthy_peers()
        if not peers:
            logger.debug("No healthy peers for replication")
            return
        
        logger.debug(f"Replicating {len(batch)} events to {len(peers)} peers")
        
        # Send to each peer (parallel)
        tasks = [
            self._replicate_to_peer(peer.server_id, peer.host, peer.port, batch)
            for peer in peers
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Mark replicated based on results
        ack_counts: Dict[str, int] = {}
        for result in results:
            if isinstance(result, dict):
                for event_id in result.get('acked_event_ids', []):
                    ack_counts[event_id] = ack_counts.get(event_id, 0) + 1
        
        # Update replication status in database
        await self._update_replication_status(batch, ack_counts)
    
    async def _replicate_to_peer(
        self,
        peer_id: str,
        host: str,
        port: int,
        batch: List[Event]
    ) -> Optional[Dict]:
        """
        Replicate batch to single peer
        
        Args:
            peer_id: Peer server ID
            host: Peer hostname
            port: Peer port
            batch: Batch of events to send
            
        Returns:
            Response with acked event IDs, or None on failure
        """
        url = f"http://{host}:{port}/api/v1/gossip/sync-state"
        
        payload = {
            'source_server_id': self.server_id,
            'timestamp': datetime.utcnow().isoformat(),
            'vector_clock': self.gossip_node.get_vector_clock(),
            'sync_events': [e.to_dict() for e in batch],
            'sync_position': len(batch),
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.replicate_timeout_sec) as client:
                response = await client.post(url, json=payload)
                
                if response.status_code == 200:
                    logger.debug(f"Replicated {len(batch)} events to {peer_id}")
                    return response.json()
                else:
                    logger.warning(f"Replication to {peer_id} returned {response.status_code}")
                    return None
        
        except asyncio.TimeoutError:
            logger.warning(f"Replication to {peer_id} timed out")
            return None
        
        except Exception as e:
            logger.warning(f"Replication to {peer_id} failed: {e}")
            return None
    
    async def _update_replication_status(self, batch: List[Event], ack_counts: Dict[str, int]):
        """
        Update database with replication status
        
        Args:
            batch: Events that were replicated
            ack_counts: Count of acks per event_id
        """
        try:
            from src.models import Event as EventModel, EventReplicationState
            
            db = self.db_session_factory()
            try:
                for event in batch:
                    ack_count = ack_counts.get(event.event_id, 0)
                    
                    # Update event replication status
                    event_record = db.query(EventModel).filter(
                        EventModel.event_id == event.event_id
                    ).first()
                    
                    if event_record:
                        event_record.is_replicated = (ack_count > 0)
                        
                        # Add replication state records
                        existing = db.query(EventReplicationState).filter(
                            EventReplicationState.event_id == event.event_id
                        ).all()
                        
                        if not existing and ack_count > 0:
                            # Add placeholder for replicated event
                            state = EventReplicationState(
                                event_id=event.event_id,
                                server_id=self.server_id,
                                acked=True,
                                acked_at=datetime.utcnow(),
                            )
                            db.add(state)
                
                db.commit()
                logger.debug(f"Updated replication status for {len(batch)} events")
            
            finally:
                db.close()
        
        except Exception as e:
            logger.error(f"Error updating replication status: {e}", exc_info=True)
    
    async def handle_replicated_event(self, event: Event) -> bool:
        """
        Handle an event received from a peer
        
        Args:
            event: Event received from peer
            
        Returns:
            True if event was applied, False if conflict/duplicate
        """
        # Check for duplicates (by event_id)
        if await self._is_duplicate_event(event.event_id):
            logger.debug(f"Duplicate event received: {event.event_id}")
            return False
        
        # Check for conflicts (concurrent operations on same account)
        concurrent, conflict_desc = await self._detect_conflicts(event)
        if concurrent:
            logger.warning(f"Conflict detected: {conflict_desc} - event: {event.event_id}")
            self.conflict_log[event.event_id] = {
                'description': conflict_desc,
                'timestamp': datetime.utcnow().isoformat(),
                'event': event.to_dict(),
            }
        
        # Apply LWW to database
        try:
            from src.models import Event as EventModel, Account
            db = self.db_session_factory()
            try:
                # 1. Fetch or create account stub
                account = db.query(Account).filter(Account.account_id == event.account_id).first()
                if not account:
                    # Create stub account
                    account = Account(
                        account_id=event.account_id,
                        phone_number=f"unknown_{event.account_id}_{event.event_id[:5]}",
                        account_holder_name="Unknown (Replicated)",
                        balance=event.balance_after or Decimal(0),
                        created_by_server=event.server_id
                    )
                    db.add(account)
                    db.flush()
                else:
                    # LWW check against account's last update
                    last_event = db.query(EventModel).filter(
                        EventModel.account_id == event.account_id
                    ).order_by(EventModel.timestamp.desc()).first()
                    
                    is_newer = True
                    if last_event and event.timestamp:
                        if last_event.timestamp > event.timestamp:
                            is_newer = False
                            logger.warning(f"LWW reject: last_event ({last_event.timestamp}) > event ({event.timestamp})")
                        elif last_event.timestamp == event.timestamp:
                            # Tie-breaker
                            if last_event.server_id > event.server_id:
                                is_newer = False
                                logger.warning(f"LWW reject tie-break: last ({last_event.server_id}) > event ({event.server_id})")
                    
                    if is_newer and event.balance_after is not None:
                        # Prevent negative balance during replication
                        new_balance = event.balance_after
                        if new_balance < 0:
                            new_balance = Decimal(0)
                            logger.warning(f"Prevented negative balance on replication for {event.account_id}")
                        
                        account.balance = new_balance
                        account.version += 1
                        account.last_modified_by_server = event.server_id
                    else:
                        logger.warning(f"Not updating balance for {event.account_id}. is_newer={is_newer}")
                
                # 2. Save event in DB
                event_record = EventModel(
                    event_id=event.event_id,
                    event_type=event.event_type.value,
                    account_id=event.account_id,
                    request_id=event.request_id,
                    amount=event.amount,
                    balance_before=event.balance_before,
                    balance_after=event.balance_after,
                    vector_clock=event.vector_clock,
                    server_id=event.server_id,
                    timestamp=event.timestamp,
                    client_reference=event.client_reference,
                    is_applied=True,
                    is_replicated=False
                )
                db.add(event_record)
                db.commit()
                
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to apply replicated event to DB: {e}")
            return False

        # Update our vector clock from event
        self.gossip_node.update_vector_clock(event.vector_clock)
        
        logger.info(f"Replicated event applied: {event.event_id}")
        return True
    
    async def _is_duplicate_event(self, event_id: str) -> bool:
        """Check if we've already seen this event"""
        try:
            from src.models import Event as EventModel
            
            db = self.db_session_factory()
            try:
                existing = db.query(EventModel).filter(
                    EventModel.event_id == event_id
                ).first()
                return existing is not None
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error checking duplicate: {e}")
            return False
    
    async def _detect_conflicts(self, event: Event) -> tuple:
        """
        Detect if event conflicts with concurrent operations
        
        Args:
            event: Event to check for conflicts
            
        Returns:
            (is_concurrent, description)
        """
        try:
            from src.models import Event as EventModel
            
            db = self.db_session_factory()
            try:
                # Get recent events on same account
                recent_events = db.query(EventModel).filter(
                    EventModel.account_id == event.account_id,
                    EventModel.event_id != event.event_id
                ).order_by(EventModel.timestamp.desc()).limit(5).all()
                
                # Check for concurrent modifications
                for recent_event in recent_events:
                    recent_vc = VectorClock(clock=recent_event.vector_clock)
                    event_vc = VectorClock(clock=event.vector_clock)
                    
                    is_concurrent, desc = detect_concurrent_operations(
                        recent_event.vector_clock,
                        event.vector_clock,
                        recent_event.account_id,
                        event.account_id
                    )
                    
                    if is_concurrent:
                        return True, desc
                
                return False, ""
            
            finally:
                db.close()
        
        except Exception as e:
            logger.error(f"Error detecting conflicts: {e}")
            return False, ""
    
    def get_conflict_log(self) -> Dict:
        """Get logged conflicts"""
        return self.conflict_log.copy()
    
    def get_replication_stats(self) -> Dict:
        """Get replication statistics"""
        return {
            'pending_replication': len(self.pending_replication),
            'conflicts_detected': len(self.conflict_log),
            'healthy_peers': len(self.gossip_node.get_healthy_peers()),
        }
