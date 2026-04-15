"""
Example test cases for Mobile Money System
"""
import pytest
from sqlalchemy.orm import Session
from decimal import Decimal
from src.models import Account
from src.core.operations import AccountOperations
from src.core.idempotency import RequestIdempotency
from src.distributed.hashing import ConsistentHash, ServerDiscovery
from src.ussd.protocol import USSDParser, USSDFormatter


class TestOperations:
    """Test account operations"""
    
    @pytest.fixture
    def test_account(self, db: Session):
        """Create test account"""
        account = Account(
            phone_number="0799999999",
            account_holder_name="Test User",
            balance=Decimal("10000.00")
        )
        db.add(account)
        db.commit()
        return account
    
    def test_withdraw_success(self, db: Session, test_account):
        """Test successful withdrawal"""
        success, message, data = AccountOperations.withdraw(
            db,
            account_id=test_account.account_id,
            phone_number="0799999999",
            amount=Decimal("1000.00"),
            request_id="test_withdraw_001"
        )
        
        assert success is True
        assert "data" in str(data)
        assert float(data["balance_after"]) == 9000.00
    
    def test_withdraw_insufficient_balance(self, db: Session, test_account):
        """Test withdrawal with insufficient balance"""
        success, message, data = AccountOperations.withdraw(
            db,
            account_id=test_account.account_id,
            phone_number="0799999999",
            amount=Decimal("15000.00"),
            request_id="test_withdraw_002"
        )
        
        assert success is False
        assert "Insufficient" in message
    
    def test_deposit_success(self, db: Session, test_account):
        """Test successful deposit"""
        success, message, data = AccountOperations.deposit(
            db,
            account_id=test_account.account_id,
            phone_number="0799999999",
            amount=Decimal("5000.00"),
            request_id="test_deposit_001"
        )
        
        assert success is True
        assert float(data["balance_after"]) == 15000.00
    
    def test_check_balance(self, db: Session, test_account):
        """Test balance check"""
        success, message, data = AccountOperations.check_balance(
            db,
            account_id=test_account.account_id
        )
        
        assert success is True
        assert float(data["balance"]) == 10000.00


class TestUSSDProtocol:
    """Test USSD protocol parsing"""
    
    def test_parse_withdraw(self):
        """Test parsing withdraw request"""
        parser = USSDParser()
        success, request, error = parser.parse("*165*2*075346363*1000#")
        
        assert success is True
        assert request.operation == "withdraw"
        assert request.phone_number == "075346363"
        assert request.amount == 1000.0
    
    def test_parse_deposit(self):
        """Test parsing deposit request"""
        parser = USSDParser()
        success, request, error = parser.parse("*165*1*075346363*500#")
        
        assert success is True
        assert request.operation == "deposit"
        assert request.amount == 500.0
    
    def test_parse_balance_check(self):
        """Test parsing balance check"""
        parser = USSDParser()
        success, request, error = parser.parse("*165*3*075346363#")
        
        assert success is True
        assert request.operation == "check_balance"
        assert request.amount is None
    
    def test_parse_invalid_operation(self):
        """Test invalid operation code"""
        parser = USSDParser()
        success, request, error = parser.parse("*165*9*075346363#")
        
        assert success is False
        assert "Invalid operation" in error
    
    def test_format_success_response(self):
        """Test response formatting"""
        formatter = USSDFormatter()
        response = formatter.success_response(
            "withdraw",
            "Withdrawal successful",
            {"balance": 9000, "currency": "KES"}
        )
        
        assert "*165*2*" in response
        assert "Balance" in response
        assert "#" in response


class TestConsistentHashing:
    """Test consistent hashing"""
    
    @pytest.fixture
    def hash_ring(self):
        """Create hash ring with test servers"""
        servers = {
            "server_1": {"host": "localhost", "port": 8001},
            "server_2": {"host": "localhost", "port": 8002},
            "server_3": {"host": "localhost", "port": 8003},
        }
        return ConsistentHash(servers, virtual_nodes=150)
    
    def test_consistent_hashing(self, hash_ring):
        """Test consistent hashing"""
        phone = "075346363"
        node1 = hash_ring.get_node(phone)
        node2 = hash_ring.get_node(phone)
        
        assert node1.node_id == node2.node_id
    
    def test_multiple_nodes(self, hash_ring):
        """Test getting multiple nodes"""
        phone = "075346363"
        nodes = hash_ring.get_nodes(phone, count=3)
        
        assert len(nodes) == 3
        assert len(set(n.node_id for n in nodes)) == 3  # All unique
    
    def test_add_remove_node(self, hash_ring):
        """Test adding and removing nodes"""
        # Get initial node
        phone = "075346363"
        initial_node = hash_ring.get_node(phone)
        
        # Add new node
        hash_ring.add_node("server_4", "localhost", 8004)
        
        # Node assignment may change (depending on hash)
        new_node = hash_ring.get_node(phone)
        # This is valid - node may or may not change
        
        # Verify all nodes exist
        all_nodes = hash_ring.get_all_nodes()
        assert len(all_nodes) == 4
        
        # Remove node
        hash_ring.remove_node("server_4")
        all_nodes = hash_ring.get_all_nodes()
        assert len(all_nodes) == 3


class TestIdempotency:
    """Test request idempotency"""
    
    def test_generate_request_id(self):
        """Test request ID generation"""
        request_id = RequestIdempotency.generate_request_id(
            "075346363",
            "withdraw",
            "ref_123"
        )
        
        assert "075346363" in request_id
        assert len(request_id) > 20  # Should be reasonably long
    
    def test_duplicate_detection(self, db: Session):
        """Test duplicate request detection"""
        request_id = "test_request_001"
        
        # Create request entry
        RequestIdempotency.create_request_entry(
            db,
            request_id,
            account_id=1,
            phone_number="075346363",
            operation_type="withdraw",
            request_data={"amount": 1000},
            client_ip="127.0.0.1"
        )
        
        # Update status to completed
        RequestIdempotency.update_request_status(
            db,
            request_id,
            "completed",
            200,
            {"balance_after": 9000}
        )
        
        # Check for duplicate
        is_dup, cached = RequestIdempotency.is_duplicate_request(db, request_id)
        
        assert is_dup is True
        assert cached is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
