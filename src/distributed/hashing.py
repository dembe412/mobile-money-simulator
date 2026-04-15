"""
Consistent Hashing for server discovery
Routes clients to nearest/optimal server using hash ring
"""
import hashlib
from typing import List, Optional, Dict
from bisect import bisect_right
import logging

logger = logging.getLogger(__name__)


class Node:
    """Represents a server node in the hash ring"""
    
    def __init__(self, node_id: str, host: str, port: int):
        self.node_id = node_id
        self.host = host
        self.port = port
    
    def __repr__(self):
        return f"Node({self.node_id}, {self.host}:{self.port})"


class ConsistentHash:
    """
    Consistent Hashing implementation with virtual nodes
    Provides load balancing and fault tolerance
    """
    
    def __init__(self, nodes: Dict[str, Dict] = None, virtual_nodes: int = 150):
        """
        Initialize hash ring
        
        Args:
            nodes: Dict of {node_id: {'host': str, 'port': int}}
            virtual_nodes: Number of virtual nodes per server for balance
        """
        self.virtual_nodes = virtual_nodes
        self.nodes: Dict[str, Node] = {}
        self.hash_ring: Dict[int, Node] = {}  # {hash_position: Node}
        self.sorted_keys: List[int] = []
        
        if nodes:
            for node_id, config in nodes.items():
                self.add_node(node_id, config['host'], config['port'])
    
    def _hash(self, key: str) -> int:
        """
        Hash function using SHA-1
        Returns integer hash position on the ring (0 to 2^32-1)
        """
        hash_obj = hashlib.sha1(key.encode('utf-8'))
        return int(hash_obj.hexdigest(), 16) % (2 ** 32)
    
    def add_node(self, node_id: str, host: str, port: int) -> None:
        """
        Add a server node to the hash ring
        
        Args:
            node_id: Unique identifier (e.g., 'server_1')
            host: Server hostname/IP
            port: Server port
        """
        if node_id in self.nodes:
            logger.warning(f"Node {node_id} already exists, skipping")
            return
        
        node = Node(node_id, host, port)
        self.nodes[node_id] = node
        
        # Add virtual nodes for better distribution
        for i in range(self.virtual_nodes):
            virtual_key = f"{node_id}:{i}"
            hash_pos = self._hash(virtual_key)
            self.hash_ring[hash_pos] = node
        
        # Keep sorted list of hash positions
        self.sorted_keys = sorted(self.hash_ring.keys())
        logger.info(f"Added node {node_id} with {self.virtual_nodes} virtual nodes")
    
    def remove_node(self, node_id: str) -> None:
        """
        Remove a server node from the hash ring
        
        Args:
            node_id: Node identifier to remove
        """
        if node_id not in self.nodes:
            logger.warning(f"Node {node_id} not found")
            return
        
        # Remove all virtual nodes
        for i in range(self.virtual_nodes):
            virtual_key = f"{node_id}:{i}"
            hash_pos = self._hash(virtual_key)
            if hash_pos in self.hash_ring:
                del self.hash_ring[hash_pos]
        
        del self.nodes[node_id]
        self.sorted_keys = sorted(self.hash_ring.keys())
        logger.info(f"Removed node {node_id}")
    
    def get_node(self, key: str) -> Optional[Node]:
        """
        Get the server node responsible for a key
        
        Args:
            key: Key to hash (usually phone number)
            
        Returns:
            Node object or None if ring is empty
        """
        if not self.hash_ring:
            return None
        
        hash_pos = self._hash(key)
        
        # Find the first node with hash >= our hash
        idx = bisect_right(self.sorted_keys, hash_pos)
        
        # Wrap around if we're at the end
        if idx == len(self.sorted_keys):
            idx = 0
        
        return self.hash_ring[self.sorted_keys[idx]]
    
    def get_nodes(self, key: str, count: int = 3) -> List[Node]:
        """
        Get multiple nodes for a key (for redundancy)
        Used for replication - returns primary + replicas
        
        Args:
            key: Key to hash
            count: Number of nodes to return
            
        Returns:
            List of Node objects
        """
        if not self.hash_ring:
            return []
        
        hash_pos = self._hash(key)
        nodes = []
        seen = set()
        
        idx = bisect_right(self.sorted_keys, hash_pos)
        
        # Get unique nodes
        while len(nodes) < count and len(nodes) < len(self.nodes):
            if idx >= len(self.sorted_keys):
                idx = 0
            
            node = self.hash_ring[self.sorted_keys[idx]]
            if node.node_id not in seen:
                nodes.append(node)
                seen.add(node.node_id)
            
            idx += 1
        
        return nodes
    
    def get_all_nodes(self) -> List[Node]:
        """
        Get all unique nodes in the ring
        
        Returns:
            List of all Node objects
        """
        return list(self.nodes.values())
    
    def get_status(self) -> Dict:
        """
        Get hash ring status information
        
        Returns:
            Dictionary with ring statistics
        """
        return {
            "total_nodes": len(self.nodes),
            "total_virtual_nodes": len(self.hash_ring),
            "virtual_nodes_per_server": self.virtual_nodes,
            "nodes": [
                {
                    "id": node.node_id,
                    "host": node.host,
                    "port": node.port
                }
                for node in self.nodes.values()
            ]
        }


class ServerDiscovery:
    """
    Server discovery and selection mechanism
    Handles routing of client requests to appropriate server
    """
    
    def __init__(self, consistent_hash: ConsistentHash):
        """
        Initialize server discovery
        
        Args:
            consistent_hash: ConsistentHash instance
        """
        self.hash_ring = consistent_hash
    
    def find_server_for_phone(self, phone_number: str) -> Optional[Node]:
        """
        Find the primary server for a phone number
        
        Args:
            phone_number: Client's phone number
            
        Returns:
            Node object representing the server
        """
        return self.hash_ring.get_node(phone_number)
    
    def find_replica_servers(
        self,
        phone_number: str,
        count: int = 2
    ) -> List[Node]:
        """
        Find replica servers for account replication
        
        Args:
            phone_number: Client's phone number
            count: Number of replicas (not including primary)
            
        Returns:
            List of Node objects
        """
        nodes = self.hash_ring.get_nodes(phone_number, count=count+1)
        # Return all except the first (primary)
        return nodes[1:count+1]
    
    def get_server_url(self, node: Optional[Node]) -> Optional[str]:
        """
        Build URL for a server node
        
        Args:
            node: Node object
            
        Returns:
            Full URL string or None
        """
        if not node:
            return None
        return f"http://{node.host}:{node.port}"
    
    def route_request(self, phone_number: str) -> Dict:
        """
        Route a request to the appropriate server
        
        Args:
            phone_number: Client phone number
            
        Returns:
            Dictionary with routing information
        """
        primary = self.find_server_for_phone(phone_number)
        replicas = self.find_replica_servers(phone_number, count=2)
        
        return {
            "phone_number": phone_number,
            "primary_server": {
                "id": primary.node_id,
                "url": self.get_server_url(primary)
            },
            "replica_servers": [
                {
                    "id": node.node_id,
                    "url": self.get_server_url(node)
                }
                for node in replicas
            ]
        }


# Example usage and testing
if __name__ == "__main__":
    # Initialize hash ring with servers
    servers = {
        "server_1": {"host": "localhost", "port": 8001},
        "server_2": {"host": "localhost", "port": 8002},
        "server_3": {"host": "localhost", "port": 8003},
    }
    
    hash_ring = ConsistentHash(servers, virtual_nodes=150)
    discovery = ServerDiscovery(hash_ring)
    
    # Test routing
    test_phones = [
        "075346363",
        "0721234567",
        "0728765432",
        "0733333333",
    ]
    
    for phone in test_phones:
        server = discovery.find_server_for_phone(phone)
        print(f"Phone {phone} -> Server {server.node_id} ({server.host}:{server.port})")
    
    # Test request routing
    routing = discovery.route_request("075346363")
    print(f"\nRouting for 075346363:")
    print(f"Primary: {routing['primary_server']}")
    print(f"Replicas: {routing['replica_servers']}")
    
    print(f"\nRing Status: {hash_ring.get_status()}")
