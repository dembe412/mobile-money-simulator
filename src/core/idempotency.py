"""
Request uniqueness, idempotency, and deduplication mechanism
Ensures "exactly-once" semantics for operations
"""
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
import logging
from typing import Tuple, Optional, Dict, Any

from src.models import Request, RequestStatus
from config.settings import server_config

logger = logging.getLogger(__name__)


class RequestIdempotency:
    """
    Handles request tracking and idempotent execution
    Prevents duplicate charge/debit in case of retries
    """
    
    @staticmethod
    def generate_request_id(
        phone_number: str,
        operation_type: str,
        client_reference: Optional[str] = None
    ) -> str:
        """
        Generate unique request ID
        
        Format: {server_id}_{timestamp_ms}_{uuid}_{phone_number}
        
        Args:
            phone_number: Client phone number
            operation_type: Type of operation
            client_reference: Optional client-provided reference
            
        Returns:
            Unique request ID string
        """
        timestamp = int(datetime.utcnow().timestamp() * 1000)
        unique_id = str(uuid.uuid4())[:8]
        
        request_id = f"{server_config.SERVER_ID}_{timestamp}_{unique_id}_{phone_number}"
        
        logger.debug(f"Generated request ID: {request_id} for {operation_type}")
        return request_id
    
    @staticmethod
    def create_request_entry(
        db: Session,
        request_id: str,
        account_id: int,
        phone_number: str,
        operation_type: str,
        request_data: Dict[str, Any],
        client_ip: str,
        ttl_seconds: int = 3600
    ) -> bool:
        """
        Create a request tracking entry
        
        Args:
            db: Database session
            request_id: Unique request identifier
            account_id: Account ID
            phone_number: Phone number
            operation_type: Operation type (withdraw, deposit, etc.)
            request_data: Request parameters as dict
            client_ip: Client IP address
            ttl_seconds: Time-to-live for request record
            
        Returns:
            True if created successfully
        """
        try:
            # Check if request already exists (duplicate)
            existing = db.query(Request).filter(
                Request.request_id == request_id
            ).first()
            
            if existing:
                logger.warning(f"Request {request_id} already exists - DUPLICATE")
                return False
            
            # Create new request entry
            request = Request(
                request_id=request_id,
                account_id=account_id,
                phone_number=phone_number,
                operation_type=operation_type,
                request_data=request_data,
                status=RequestStatus.RECEIVED.value,
                client_ip=client_ip,
                server_id=server_config.SERVER_ID,
                expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds)
            )
            
            db.add(request)
            db.commit()
            
            logger.info(f"Request {request_id} created for {operation_type}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create request entry: {str(e)}")
            return False
    
    @staticmethod
    def get_request(db: Session, request_id: str) -> Optional[Request]:
        """
        Get request by ID
        
        Args:
            db: Database session
            request_id: Request identifier
            
        Returns:
            Request object or None
        """
        return db.query(Request).filter(
            Request.request_id == request_id
        ).first()
    
    @staticmethod
    def is_duplicate_request(db: Session, request_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check if request is a duplicate and if so, return cached response
        
        Args:
            db: Database session
            request_id: Request identifier
            
        Returns:
            (is_duplicate: bool, cached_response: dict or None)
        """
        request = RequestIdempotency.get_request(db, request_id)
        
        if not request:
            return False, None
        
        # Check if not expired
        if request.expires_at and datetime.utcnow() > request.expires_at:
            logger.info(f"Request {request_id} expired")
            return False, None
        
        # Check if completed
        if request.status == RequestStatus.COMPLETED.value:
            logger.info(f"Request {request_id} is duplicate, returning cached response")
            return True, request.response_data
        
        return False, None
    
    @staticmethod
    def update_request_status(
        db: Session,
        request_id: str,
        status: str,
        response_code: int = None,
        response_data: Dict = None,
        error_message: str = None
    ) -> bool:
        """
        Update request status and response
        
        Args:
            db: Database session
            request_id: Request identifier
            status: New status (completed, failed, processing)
            response_code: HTTP response code
            response_data: Response data as dict
            error_message: Error message if failed
            
        Returns:
            True if updated successfully
        """
        try:
            request = db.query(Request).filter(
                Request.request_id == request_id
            ).first()
            
            if not request:
                logger.warning(f"Request {request_id} not found for update")
                return False
            
            request.status = status
            request.response_code = response_code or 200
            request.response_data = response_data
            request.error_message = error_message
            request.updated_at = datetime.utcnow()
            
            db.add(request)
            db.commit()
            
            logger.info(f"Request {request_id} updated to status {status}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update request: {str(e)}")
            return False
    
    @staticmethod
    def cleanup_expired_requests(db: Session) -> int:
        """
        Remove expired request entries to save space
        Called periodically by background worker
        
        Args:
            db: Database session
            
        Returns:
            Number of requests deleted
        """
        try:
            deleted = db.query(Request).filter(
                Request.expires_at <= datetime.utcnow()
            ).delete()
            
            db.commit()
            logger.info(f"Cleaned up {deleted} expired requests")
            return deleted
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to cleanup requests: {str(e)}")
            return 0
