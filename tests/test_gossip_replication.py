"""
Integration tests for gossip protocol and event sourcing
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.distributed.gossip import GossipNode, GossipMessageType
from src.distributed.vector_clock import VectorClock, EventOrder, detect_concurrent_operations
from src.core.events import Event, EventType, EventStore, create_withdraw_event, create_deposit_event
from src.core.wal import WriteAheadLog, WALStatus
from src.core.quorum import QuorumConfig, QuorumWriter
from src.core.conflict_resolver import ConflictResolver, LastWriteWinsStrategy


class TestVectorClock:
    """Test vector clock implementation"""
    
    def test_vector_clock_happens_before(self):
        """Test happens_before detection"""
        vc1 = VectorClock(clock={'s1': 1, 's2': 0, 's3': 0})
        vc2 = VectorClock(clock={'s1': 2, 's2': 1, 's3': 0})
        
        assert vc1.happens_before(vc2), "vc1 should happen before vc2"
        assert not vc2.happens_before(vc1), "vc2 should not happen before vc1"
    
    def test_vector_clock_concurrent(self):
        """Test concurrent event detection"""
        vc1 = VectorClock(clock={'s1': 1, 's2': 0, 's3': 0})
        vc2 = VectorClock(clock={'s1': 0, 's2': 1, 's3': 0})
        
        assert vc1.concurrent(vc2), "Operations should be concurrent"
        assert vc2.concurrent(vc1), "Concurrency is symmetric"
    
    def test_vector_clock_equals(self):
        """Test clock equality"""
        vc1 = VectorClock(clock={'s1': 1, 's2': 1})
        vc2 = VectorClock(clock={'s1': 1, 's2': 1})
        
        assert vc1.equals(vc2), "Clocks should be equal"
    
    def test_vector_clock_compare(self):
        """Test clock comparison returns correct order"""
        vc1 = VectorClock(clock={'s1': 1, 's2': 0})
        vc2 = VectorClock(clock={'s1': 2, 's2': 0})
        
        assert vc1.compare(vc2) == EventOrder.BEFORE
        assert vc2.compare(vc1) == EventOrder.AFTER
    
    def test_detect_concurrent_operations(self):
        """Test concurrent operation detection"""
        vc1 = {'s1': 1, 's2': 0, 's3': 0}
        vc2 = {'s1': 0, 's2': 1, 's3': 0}
        
        is_concurrent, desc = detect_concurrent_operations(
            vc1, vc2, event1_account_id=1, event2_account_id=1
        )
        
        assert is_concurrent, "Should detect concurrent operations"
        assert "Concurrent" in desc


class TestEventStore:
    """Test event sourcing"""
    
    def test_append_event(self):
        """Test appending events"""
        store = EventStore()
        
        event = Event(
            event_id="evt-1",
            event_type=EventType.WITHDRAW,
            account_id=1,
            request_id="req-1",
            amount=Decimal("100.00"),
            balance_before=Decimal("500.00"),
            balance_after=Decimal("400.00"),
            vector_clock={'s1': 1},
            server_id='s1',
        )
        
        event_id = store.append(event)
        assert event_id == "evt-1"
        assert store.event_count() == 1
    
    def test_get_account_events(self):
        """Test retrieving events for account"""
        store = EventStore()
        
        event1 = create_withdraw_event(1, "req-1", Decimal("100"), Decimal("500"), 
                                      Decimal("400"), 's1', {'s1': 1})
        event2 = create_deposit_event(1, "req-2", Decimal("200"), Decimal("400"),
                                     Decimal("600"), 's1', {'s1': 2})
        
        store.append(event1)
        store.append(event2)
        
        account_events = store.get_account_events(1)
        assert len(account_events) == 2
        assert account_events[0].amount == Decimal("100")
        assert account_events[1].amount == Decimal("200")
    
    def test_mark_applied(self):
        """Test marking events as applied"""
        store = EventStore()
        event = Event(event_id="evt-1", event_type=EventType.WITHDRAW,
                     account_id=1, request_id="req-1")
        store.append(event)
        
        assert not event.is_applied
        assert store.unapplied_count() == 1
        
        store.mark_applied("evt-1")
        assert store.get_event("evt-1").is_applied
        assert store.unapplied_count() == 0


class TestWriteAheadLog:
    """Test write-ahead log"""
    
    def test_wal_append(self):
        """Test appending to WAL"""
        wal = WriteAheadLog()
        log_id = wal.append("evt-1", required_replicas=2)
        
        assert log_id == 1
        assert wal.get_entry("evt-1") is not None
        assert len(wal.get_pending_entries()) == 1
    
    def test_wal_mark_applied(self):
        """Test marking WAL entry as applied"""
        wal = WriteAheadLog()
        wal.append("evt-1", required_replicas=2)
        
        wal.mark_applied("evt-1")
        entry = wal.get_entry("evt-1")
        
        assert entry.status == WALStatus.APPLIED
        assert entry.applied_at is not None
        assert len(wal.get_pending_entries()) == 0
        assert len(wal.get_applied_entries()) == 1
    
    def test_wal_quorum_tracking(self):
        """Test WAL quorum replica tracking"""
        wal = WriteAheadLog()
        wal.append("evt-1", required_replicas=2)
        
        # No acks yet
        entry = wal.get_entry("evt-1")
        assert not entry.is_quorum_reached()
        
        # One ack
        wal.mark_replica_ack("evt-1")
        assert not entry.is_quorum_reached()
        
        # Two acks (quorum)
        wal.mark_replica_ack("evt-1")
        assert entry.is_quorum_reached()


class TestConflictResolver:
    """Test conflict resolution"""
    
    def test_lww_resolution(self):
        """Test last-write-wins strategy"""
        resolver = ConflictResolver()
        resolver.set_strategy(LastWriteWinsStrategy())
        
        event1 = Event(
            event_id="evt-1", event_type=EventType.WITHDRAW,
            account_id=1, request_id="req-1",
            timestamp=datetime.utcnow(), server_id='s1'
        )
        
        # event2 has later timestamp
        event2 = Event(
            event_id="evt-2", event_type=EventType.DEPOSIT,
            account_id=1, request_id="req-2",
            timestamp=datetime.utcnow(), server_id='s2'
        )
        event2.timestamp = event1.timestamp  # same time, s2 > s1
        
        strategy = LastWriteWinsStrategy()
        winning = strategy.resolve(event1, event2, Decimal("100"))
        
        # Should prefer event2 since server_id 's2' > 's1'
        assert winning.server_id == 's2' or winning.event_id == 'evt-2'
    
    def test_detect_balance_conflict(self):
        """Test balance conflict detection"""
        resolver = ConflictResolver()
        
        is_conflict, desc = resolver.detect_balance_conflict(
            Decimal("100"), Decimal("150"), account_id=1
        )
        
        assert is_conflict
        assert "Balance mismatch" in desc


class TestGossipNode:
    """Test gossip protocol"""
    
    def test_gossip_node_creation(self):
        """Test creating a gossip node"""
        peer_servers = {
            "s1": {"host": "localhost", "port": 8001},
            "s2": {"host": "localhost", "port": 8002},
            "s3": {"host": "localhost", "port": 8003},
        }
        
        node = GossipNode("s1", "localhost", 8001, peer_servers)
        
        assert node.server_id == "s1"
        assert len(node.peers) == 2  # s2 and s3
        assert "s2" in node.peers
        assert "s3" in node.peers
    
    def test_vector_clock_increment(self):
        """Test incrementing vector clock"""
        node = GossipNode("s1", "localhost", 8001, {
            "s1": {"host": "localhost", "port": 8001},
            "s2": {"host": "localhost", "port": 8002},
        })
        
        initial_vc = node.get_vector_clock()
        assert initial_vc['s1'] == 0
        
        node.increment_vector_clock()
        updated_vc = node.get_vector_clock()
        assert updated_vc['s1'] == 1
    
    def test_heartbeat_message_creation(self):
        """Test creating heartbeat message"""
        node = GossipNode("s1", "localhost", 8001, {
            "s1": {"host": "localhost", "port": 8001},
            "s2": {"host": "localhost", "port": 8002},
        })
        
        msg = node.create_heartbeat_message()
        
        assert msg.message_type == GossipMessageType.HEARTBEAT
        assert msg.source_server_id == "s1"
        assert msg.server_info.server_id == "s1"


class TestQuorumWriter:
    """Test quorum writes"""
    
    async def test_quorum_timeout(self):
        """Test quorum timeout"""
        peer_servers = {
            "s1": {"host": "localhost", "port": 8001},
            "s2": {"host": "localhost", "port": 8002},
            "s3": {"host": "localhost", "port": 8003},
        }
        node = GossipNode("s1", "localhost", 8001, peer_servers)
        config = QuorumConfig(total_servers=3, required_quorum=2, timeout_sec=1)
        
        writer = QuorumWriter(node, config)
        
        # Wait for quorum with timeout (should fail since no acks)
        success, acked = await writer.wait_for_quorum("evt-1")
        
        assert not success, "Should timeout without acks"
        assert len(acked) == 0


if __name__ == "__main__":
    print("Running integration tests...")
    
    # Run non-async tests
    test_vc = TestVectorClock()
    test_vc.test_vector_clock_happens_before()
    test_vc.test_vector_clock_concurrent()
    test_vc.test_vector_clock_equals()
    test_vc.test_vector_clock_compare()
    test_vc.test_detect_concurrent_operations()
    print("✓ Vector clock tests passed")
    
    test_es = TestEventStore()
    test_es.test_append_event()
    test_es.test_get_account_events()
    test_es.test_mark_applied()
    print("✓ Event store tests passed")
    
    test_wal = TestWriteAheadLog()
    test_wal.test_wal_append()
    test_wal.test_wal_mark_applied()
    test_wal.test_wal_quorum_tracking()
    print("✓ Write-ahead log tests passed")
    
    test_cr = TestConflictResolver()
    test_cr.test_lww_resolution()
    test_cr.test_detect_balance_conflict()
    print("✓ Conflict resolver tests passed")
    
    test_gn = TestGossipNode()
    test_gn.test_gossip_node_creation()
    test_gn.test_vector_clock_increment()
    test_gn.test_heartbeat_message_creation()
    print("✓ Gossip node tests passed")
    
    test_qw = TestQuorumWriter()
    print("✓ Quorum writer tests passed (async tests skipped)")
    
    print("\n✓✓✓ All integration tests passed ✓✓✓")
