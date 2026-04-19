"""
Quorum write implementation for strong consistency on critical operations
Waits for acknowledgement from majority of peers before responding
"""
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

from src.distributed.gossip import GossipNode

logger = logging.getLogger(__name__)


class QuorumConfig:
    """Configuration for quorum writes"""
    
    def __init__(
        self,
        total_servers: int = 3,
        required_quorum: int = 2,  # 2/3 majority
        timeout_sec: int = 5,
    ):
        """
        Initialize quorum config
        
        Args:
            total_servers: Total number of servers in cluster
            required_quorum: How many servers needed for quorum (usually >N/2)
            timeout_sec: How long to wait for quorum acks
        """
        self.total_servers = total_servers
        self.required_quorum = required_quorum
        self.timeout_sec = timeout_sec
        
        if required_quorum <= total_servers / 2:
            logger.warning(
                f"Quorum size {required_quorum} is not > N/2 ({total_servers/2}), "
                f"strong consistency not guaranteed"
            )
    
    def __repr__(self):
        return (f"QuorumConfig(total={self.total_servers}, "
               f"required={self.required_quorum}, "
               f"timeout={self.timeout_sec}s)")


class QuorumWriter:
    """
    Manages quorum-based writes
    
    For critical operations (transfers), wait for acknowledgement from
    quorum of peers before confirming operation.
    """
    
    def __init__(self, gossip_node: GossipNode, config: QuorumConfig):
        """
        Initialize quorum writer
        
        Args:
            gossip_node: GossipNode for peer management
            config: QuorumConfig with settings
        """
        self.gossip_node = gossip_node
        self.config = config
        
        # Track pending acks
        self.pending_acks: Dict[str, {
            'event_id': str,
            'ack_from': set,
            'created_at': datetime,
        }] = {}
    
    async def wait_for_quorum(self, event_id: str) -> Tuple[bool, List[str]]:
        """
        Wait for quorum acknowledgement
        
        Args:
            event_id: Event ID to wait for
            
        Returns:
            (success, list_of_acked_servers)
            
        Raises:
            asyncio.TimeoutError: If quorum not reached within timeout
        """
        self.pending_acks[event_id] = {
            'event_id': event_id,
            'ack_from': set(),
            'created_at': datetime.utcnow(),
        }
        
        try:
            # Wait for quorum acks or timeout
            start_time = datetime.utcnow()
            deadline = start_time + timedelta(seconds=self.config.timeout_sec)
            
            while datetime.utcnow() < deadline:
                acked_from = self.pending_acks[event_id]['ack_from']
                
                # Count this server + acks from peers
                ack_count = len(acked_from) + 1  # +1 for self
                
                if ack_count >= self.config.required_quorum:
                    logger.info(f"Quorum reached for {event_id}: {ack_count}/{self.config.required_quorum} acks")
                    return True, list(acked_from)
                
                # Wait a bit before checking again
                await asyncio.sleep(0.1)
            
            # Timeout
            acked_from = self.pending_acks[event_id]['ack_from']
            ack_count = len(acked_from) + 1
            logger.warning(
                f"Quorum timeout for {event_id}: only {ack_count}/{self.config.required_quorum} acks "
                f"from {list(acked_from)}"
            )
            return False, list(acked_from)
        
        finally:
            # Clean up
            self.pending_acks.pop(event_id, None)
    
    def record_ack(self, event_id: str, server_id: str):
        """
        Record acknowledgement from peer
        
        Args:
            event_id: Event that was acked
            server_id: Peer that acked
        """
        if event_id in self.pending_acks:
            self.pending_acks[event_id]['ack_from'].add(server_id)
            logger.debug(f"ACK received from {server_id} for event {event_id}")
    
    def is_quorum_operation(self, operation_type: str) -> bool:
        """
        Check if operation type requires quorum writes
        
        Args:
            operation_type: Type of operation (withdraw, deposit, transfer, etc.)
            
        Returns:
            True if operation should use quorum writes
        """
        # Define which operations need quorum
        quorum_operations = ['transfer', 'large_withdrawal']
        return operation_type in quorum_operations
    
    def get_quorum_stats(self) -> Dict:
        """Get quorum write statistics"""
        return {
            'config': {
                'total_servers': self.config.total_servers,
                'required_quorum': self.config.required_quorum,
                'timeout_sec': self.config.timeout_sec,
            },
            'pending_acks': len(self.pending_acks),
            'healthy_peers': len(self.gossip_node.get_healthy_peers()),
        }


class QuorumValidator:
    """Validate quorum consistency"""
    
    @staticmethod
    def can_reach_quorum(healthy_peers: int, total_peers: int, required_quorum: int) -> bool:
        """
        Check if quorum can be reached given current peer health
        
        Args:
            healthy_peers: Number of healthy peers (not including self)
            total_peers: Total number of peers
            required_quorum: Required quorum size
            
        Returns:
            True if quorum can be reached with current peer state
        """
        # Count self + healthy peers
        total_available = healthy_peers + 1
        can_reach = total_available >= required_quorum
        
        logger.debug(
            f"Quorum check: available={total_available} "
            f"(self + {healthy_peers} healthy), "
            f"required={required_quorum}, "
            f"can_reach={can_reach}"
        )
        
        return can_reach
    
    @staticmethod
    def is_partition_tolerant(
        reachable_servers: int,
        total_servers: int,
        required_quorum: int
    ) -> bool:
        """
        Check if system is partition tolerant
        
        In a network partition:
        - One partition might have quorum, other won't
        - Write-quorum makes it safe (require quorum for writes)
        - But some reads might return stale data
        
        Args:
            reachable_servers: Servers reachable from this node
            total_servers: Total servers in cluster
            required_quorum: Quorum size
            
        Returns:
            True if partition won't cause data loss
        """
        # If we can reach quorum, partition is tolerated
        return reachable_servers >= required_quorum
