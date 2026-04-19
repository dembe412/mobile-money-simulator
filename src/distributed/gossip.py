"""
Gossip Protocol for peer-to-peer communication and state synchronization
Implements HTTP-based gossip with heartbeats, membership tracking, and event propagation
"""
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class GossipMessageType(str, Enum):
    """Types of gossip messages"""
    HEARTBEAT = "heartbeat"
    EVENT_BROADCAST = "event_broadcast"
    STATE_SYNC = "state_sync"
    ACK = "ack"


@dataclass
class PeerInfo:
    """Information about a peer server"""
    server_id: str
    host: str
    port: int
    status: str = "online"  # online, offline, degraded
    last_contact: Optional[datetime] = None
    vector_clock: Optional[Dict[str, int]] = None
    sync_position: int = 0
    ops_behind: int = 0
    pending_events_count: int = 0
    error_count: int = 0
    latency_ms: float = 0.0
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        d = asdict(self)
        if self.last_contact:
            d['last_contact'] = self.last_contact.isoformat()
        return d
    
    def is_alive(self, heartbeat_timeout_sec: int = 10) -> bool:
        """Check if peer is still alive based on last contact"""
        if not self.last_contact:
            return False
        time_since_contact = datetime.utcnow() - self.last_contact
        return time_since_contact.total_seconds() < heartbeat_timeout_sec


@dataclass
class GossipMessage:
    """Gossip protocol message"""
    message_type: GossipMessageType
    source_server_id: str
    timestamp: datetime
    vector_clock: Dict[str, int]
    
    # Heartbeat payload
    server_info: Optional[PeerInfo] = None
    peer_list: Optional[List[PeerInfo]] = None
    
    # Event broadcast payload
    event_id: Optional[str] = None
    event_data: Optional[Dict] = None
    
    # State sync payload
    sync_events: Optional[List[Dict]] = None
    sync_position: int = 0
    
    # Acknowledgement payload
    acked_event_ids: Optional[List[str]] = None
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        d = {
            'message_type': self.message_type.value,
            'source_server_id': self.source_server_id,
            'timestamp': self.timestamp.isoformat(),
            'vector_clock': self.vector_clock,
        }
        if self.server_info:
            d['server_info'] = self.server_info.to_dict()
        if self.peer_list:
            d['peer_list'] = [p.to_dict() for p in self.peer_list]
        if self.event_id:
            d['event_id'] = self.event_id
        if self.event_data:
            d['event_data'] = self.event_data
        if self.sync_events:
            d['sync_events'] = self.sync_events
        if self.sync_position:
            d['sync_position'] = self.sync_position
        if self.acked_event_ids:
            d['acked_event_ids'] = self.acked_event_ids
        return d


class GossipNode:
    """
    A node in the gossip protocol network
    Manages peers, sends/receives messages, tracks state
    """
    
    def __init__(
        self,
        server_id: str,
        host: str,
        port: int,
        peer_servers: Dict[str, Dict],
        heartbeat_interval_sec: int = 5,
        heartbeat_timeout_sec: int = 10,
    ):
        """
        Initialize gossip node
        
        Args:
            server_id: This server's ID
            host: This server's host
            port: This server's port
            peer_servers: Dict of {server_id: {host, port}} for other servers
            heartbeat_interval_sec: How often to send heartbeats
            heartbeat_timeout_sec: How long before marking peer dead
        """
        self.server_id = server_id
        self.host = host
        self.port = port
        self.heartbeat_interval_sec = heartbeat_interval_sec
        self.heartbeat_timeout_sec = heartbeat_timeout_sec
        
        # Vector clock: {server_id: sequence_number}
        self.vector_clock: Dict[str, int] = {}
        
        # Peers
        self.peers: Dict[str, PeerInfo] = {}
        self._init_peers(peer_servers)
        
        # Event tracking
        self.pending_event_ids: Set[str] = set()  # events waiting for replication
        self.last_sync_time = datetime.utcnow()
        
        logger.info(f"Gossip node initialized: {server_id} at {host}:{port}")
    
    def _init_peers(self, peer_servers: Dict[str, Dict]):
        """Initialize peer list from configuration"""
        for server_id, config in peer_servers.items():
            if server_id != self.server_id:  # don't add ourselves
                self.peers[server_id] = PeerInfo(
                    server_id=server_id,
                    host=config['host'],
                    port=config['port'],
                    status="offline",
                    vector_clock={s: 0 for s in peer_servers.keys()}
                )
        
        # Initialize our vector clock
        for server_id in peer_servers.keys():
            self.vector_clock[server_id] = 0
        
        logger.info(f"Initialized {len(self.peers)} peer(s): {list(self.peers.keys())}")
    
    def increment_vector_clock(self):
        """Increment our clock entry (called after applying event)"""
        self.vector_clock[self.server_id] = self.vector_clock.get(self.server_id, 0) + 1
    
    def update_vector_clock(self, remote_clock: Dict[str, int]):
        """
        Update vector clock from received message (merge clocks)
        
        Args:
            remote_clock: Vector clock from remote peer
        """
        for server_id, remote_version in remote_clock.items():
            local_version = self.vector_clock.get(server_id, 0)
            self.vector_clock[server_id] = max(local_version, remote_version)
        
        # Increment our own after merging
        self.vector_clock[self.server_id] = self.vector_clock.get(self.server_id, 0) + 1
    
    def get_vector_clock(self) -> Dict[str, int]:
        """Get current vector clock state"""
        return self.vector_clock.copy()
    
    def create_heartbeat_message(self, peer_list: Optional[List[PeerInfo]] = None) -> GossipMessage:
        """
        Create a heartbeat message to send to peers
        
        Args:
            peer_list: Optional list of known peers to include
            
        Returns:
            GossipMessage with heartbeat payload
        """
        self_info = PeerInfo(
            server_id=self.server_id,
            host=self.host,
            port=self.port,
            status="online",
            vector_clock=self.get_vector_clock(),
            sync_position=0,
            ops_behind=0,
        )
        
        return GossipMessage(
            message_type=GossipMessageType.HEARTBEAT,
            source_server_id=self.server_id,
            timestamp=datetime.utcnow(),
            vector_clock=self.get_vector_clock(),
            server_info=self_info,
            peer_list=peer_list or list(self.peers.values())
        )
    
    def create_event_broadcast_message(self, event_id: str, event_data: Dict) -> GossipMessage:
        """
        Create event broadcast message
        
        Args:
            event_id: Unique event identifier
            event_data: Event data to broadcast
            
        Returns:
            GossipMessage with event payload
        """
        return GossipMessage(
            message_type=GossipMessageType.EVENT_BROADCAST,
            source_server_id=self.server_id,
            timestamp=datetime.utcnow(),
            vector_clock=self.get_vector_clock(),
            event_id=event_id,
            event_data=event_data
        )
    
    def create_ack_message(self, acked_event_ids: List[str]) -> GossipMessage:
        """
        Create acknowledgement message for events
        
        Args:
            acked_event_ids: List of event IDs being acknowledged
            
        Returns:
            GossipMessage with ack payload
        """
        return GossipMessage(
            message_type=GossipMessageType.ACK,
            source_server_id=self.server_id,
            timestamp=datetime.utcnow(),
            vector_clock=self.get_vector_clock(),
            acked_event_ids=acked_event_ids
        )
    
    def handle_heartbeat(self, message: GossipMessage) -> None:
        """
        Handle received heartbeat message
        Updates peer status and vector clock
        
        Args:
            message: GossipMessage with heartbeat payload
        """
        peer_id = message.source_server_id
        
        if peer_id not in self.peers:
            logger.warning(f"Received heartbeat from unknown peer: {peer_id}")
            return
        
        # Update peer info
        peer = self.peers[peer_id]
        peer.last_contact = datetime.utcnow()
        peer.status = "online"
        peer.vector_clock = message.vector_clock.copy() if message.vector_clock else peer.vector_clock
        
        # Merge vector clocks
        self.update_vector_clock(message.vector_clock)
        
        logger.debug(f"Heartbeat received from {peer_id}: status={peer.status}, vc={message.vector_clock}")
    
    def mark_peer_offline(self, server_id: str):
        """Mark a peer as offline"""
        if server_id in self.peers:
            self.peers[server_id].status = "offline"
            logger.warning(f"Peer {server_id} marked offline")
    
    def get_healthy_peers(self) -> List[PeerInfo]:
        """Get list of healthy (online) peers"""
        return [p for p in self.peers.values() if p.is_alive(self.heartbeat_timeout_sec)]
    
    def get_all_peers(self) -> List[PeerInfo]:
        """Get all known peers"""
        return list(self.peers.values())
    
    def get_peer(self, server_id: str) -> Optional[PeerInfo]:
        """Get specific peer info"""
        return self.peers.get(server_id)
    
    def queue_event_for_replication(self, event_id: str):
        """Queue event for replication to peers"""
        self.pending_event_ids.add(event_id)
    
    def get_pending_events(self) -> Set[str]:
        """Get pending events waiting for replication"""
        return self.pending_event_ids.copy()
    
    def mark_event_replicated(self, event_id: str):
        """Mark event as replicated"""
        self.pending_event_ids.discard(event_id)
    
    def get_gossip_stats(self) -> Dict:
        """Get gossip protocol statistics"""
        healthy = len(self.get_healthy_peers())
        return {
            'server_id': self.server_id,
            'healthy_peers': healthy,
            'total_peers': len(self.peers),
            'pending_events': len(self.pending_event_ids),
            'vector_clock': self.get_vector_clock(),
            'peers': {p.server_id: {
                'status': p.status,
                'last_contact': p.last_contact.isoformat() if p.last_contact else None,
                'ops_behind': p.ops_behind,
            } for p in self.peers.values()}
        }
