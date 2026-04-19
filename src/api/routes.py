"""
FastAPI routes and API endpoints
"""
from fastapi import FastAPI, HTTPException, Request, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
from decimal import Decimal
import asyncio

from config.database import SessionLocal, get_db, init_db
from config.settings import server_config, app_config, security_config
from src.core.operations import AccountOperations
from src.core.idempotency import RequestIdempotency
from src.ussd.protocol import USSDParser, USSDFormatter
from src.distributed.hashing import ConsistentHash, ServerDiscovery
from src.distributed.gossip import GossipNode
from src.distributed.heartbeat_worker import HeartbeatWorker
from src.distributed.replication_manager import ReplicationManager
from src.core.events import EventStore
from src.core.wal import WriteAheadLog
from src.core.quorum import QuorumConfig, QuorumWriter
from src.core.conflict_resolver import ConflictResolver
from src.models import Account

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=app_config.APP_NAME,
    version=app_config.APP_VERSION,
    description="Distributed Mobile Money System"
)

# Initialize hash ring for server discovery
peer_servers = {
    "server_1": {"host": "localhost", "port": 8001},
    "server_2": {"host": "localhost", "port": 8002},
    "server_3": {"host": "localhost", "port": 8003},
}
hash_ring = ConsistentHash(peer_servers, virtual_nodes=150)
discovery = ServerDiscovery(hash_ring)

# Gossip protocol components (initialized at startup)
gossip_node: Optional[GossipNode] = None
heartbeat_worker: Optional[HeartbeatWorker] = None
replication_manager: Optional[ReplicationManager] = None
event_store: Optional[EventStore] = None
write_ahead_log: Optional[WriteAheadLog] = None
quorum_writer: Optional[QuorumWriter] = None
conflict_resolver: Optional[ConflictResolver] = None

# Request models
class WithdrawRequest(BaseModel):
    account_id: Optional[int] = None
    phone_number: str
    amount: float
    client_ip: str = "127.0.0.1"
    client_reference: Optional[str] = None


class DepositRequest(BaseModel):
    account_id: Optional[int] = None
    phone_number: str
    amount: float
    client_ip: str = "127.0.0.1"
    client_reference: Optional[str] = None


class BalanceRequest(BaseModel):
    account_id: Optional[int] = None
    phone_number: Optional[str] = None
    client_ip: str = "127.0.0.1"


class TransferRequest(BaseModel):
    from_account_id: int
    from_phone_number: str
    to_phone_number: str
    amount: float
    client_ip: str = "127.0.0.1"
    client_reference: Optional[str] = None


class USSDRequest(BaseModel):
    ussd_input: str
    phone_number: Optional[str] = None
    session_id: Optional[str] = None
    client_ip: str = "127.0.0.1"


class CreateAccountRequest(BaseModel):
    phone_number: str
    account_holder_name: str
    initial_balance: float = 0.0


# ============================================
# Startup & Shutdown
# ============================================

@app.on_event("startup")
async def startup_event():
    """Initialize database and start background workers"""
    global gossip_node, heartbeat_worker, replication_manager
    global event_store, write_ahead_log, quorum_writer, conflict_resolver
    
    logger.info(f"Starting Mobile Money Server: {server_config.SERVER_ID}")
    try:
        # Initialize database
        init_db()
        logger.info("Database initialized successfully")
        
        # Initialize event sourcing components
        event_store = EventStore()
        write_ahead_log = WriteAheadLog()
        conflict_resolver = ConflictResolver()
        logger.info("Event sourcing components initialized")
        
        # Initialize gossip protocol
        gossip_node = GossipNode(
            server_id=server_config.SERVER_ID,
            host=server_config.SERVER_HOST,
            port=server_config.SERVER_PORT,
            peer_servers=peer_servers,
            heartbeat_interval_sec=5,
            heartbeat_timeout_sec=10,
        )
        logger.info("Gossip node initialized")
        
        # Initialize quorum writer
        quorum_config = QuorumConfig(
            total_servers=len(peer_servers),
            required_quorum=2,  # 2/3 majority
            timeout_sec=5,
        )
        quorum_writer = QuorumWriter(gossip_node, quorum_config)
        logger.info(f"Quorum writer initialized: {quorum_config}")
        
        # Start heartbeat worker
        heartbeat_worker = HeartbeatWorker(
            gossip_node=gossip_node,
            db_session_factory=SessionLocal,
            interval_sec=5,
            timeout_sec=3,
        )
        await heartbeat_worker.start()
        logger.info("Heartbeat worker started")
        
        # Start replication manager
        replication_manager = ReplicationManager(
            gossip_node=gossip_node,
            server_id=server_config.SERVER_ID,
            db_session_factory=SessionLocal,
            batch_size=10,
            batch_interval_sec=2,
            replicate_timeout_sec=5,
        )
        await replication_manager.start()
        logger.info("Replication manager started")
        
        logger.info("✓ All startup tasks completed")
    
    except Exception as e:
        logger.error(f"Startup failed: {str(e)}", exc_info=True)
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global heartbeat_worker, replication_manager
    
    logger.info("Shutting down server...")
    try:
        if heartbeat_worker:
            await heartbeat_worker.stop()
            logger.info("Heartbeat worker stopped")
        
        if replication_manager:
            await replication_manager.stop()
            logger.info("Replication manager stopped")
        
        logger.info("✓ Shutdown complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}", exc_info=True)


# ============================================
# Health & Status
# ============================================

@app.get("/health")
async def health_check():
    """Server health check endpoint"""
    return {
        "status": "healthy",
        "server_id": server_config.SERVER_ID,
        "server_name": server_config.SERVER_NAME,
        "version": app_config.APP_VERSION
    }


@app.get("/status")
async def server_status():
    """Get detailed server status"""
    return {
        "server_id": server_config.SERVER_ID,
        "server_name": server_config.SERVER_NAME,
        "host": server_config.SERVER_HOST,
        "port": server_config.SERVER_PORT,
        "environment": app_config.APP_ENV,
        "version": app_config.APP_VERSION,
        "hash_ring_status": hash_ring.get_status()
    }


# ============================================
# Account Management
# ============================================

@app.post("/api/v1/account/create")
async def create_account(req: CreateAccountRequest, db: Session = Depends(get_db)):
    """Create a new account"""
    try:
        # Check if phone exists
        existing = db.query(Account).filter(
            Account.phone_number == req.phone_number
        ).first()
        
        if existing:
            raise HTTPException(status_code=400, detail="Account already exists")
        
        # Create account
        account = Account(
            phone_number=req.phone_number,
            account_holder_name=req.account_holder_name,
            balance=Decimal(str(req.initial_balance)),
            created_by_server=server_config.SERVER_ID
        )
        
        db.add(account)
        db.commit()
        
        logger.info(f"Account created: {req.phone_number}")
        return {
            "status": "success",
            "account_id": account.account_id,
            "phone_number": account.phone_number,
            "balance": float(account.balance)
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Account creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/account/{account_id}")
async def get_account(account_id: int, db: Session = Depends(get_db)):
    """Get account details"""
    try:
        account = db.query(Account).filter(
            Account.account_id == account_id
        ).first()
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        return {
            "account_id": account.account_id,
            "phone_number": account.phone_number,
            "name": account.account_holder_name,
            "balance": float(account.balance),
            "currency": account.currency,
            "status": account.account_status,
            "created_at": account.created_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Account query failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Core Operations
# ============================================

@app.post("/api/v1/operation/withdraw")
async def withdraw(req: WithdrawRequest, db: Session = Depends(get_db)):
    """
    Withdraw funds from account
    Synchronous operation - returns immediate response
    """
    try:
        # Resolve account by phone_number or account_id
        acc_resolved, acc_msg, account = AccountOperations.resolve_account(
            db, req.account_id, req.phone_number
        )
        
        if not acc_resolved:
            raise HTTPException(status_code=404, detail=acc_msg)
        
        account_id = account.account_id
        
        # Generate request ID for idempotency
        request_id = RequestIdempotency.generate_request_id(
            req.phone_number,
            "withdraw",
            req.client_reference
        )
        
        # Check for duplicate request
        is_dup, cached_response = RequestIdempotency.is_duplicate_request(db, request_id)
        if is_dup:
            return {
                "status": "success",
                "message": "Duplicate request - cached response",
                "data": cached_response,
                "request_id": request_id
            }
        
        # Create request entry
        RequestIdempotency.create_request_entry(
            db, request_id, account_id, req.phone_number,
            "withdraw", {"amount": req.amount}, req.client_ip
        )
        
        # Execute withdrawal
        success, message, response_data = AccountOperations.withdraw(
            db, account_id, req.phone_number,
            Decimal(str(req.amount)), request_id
        )
        
        # Update request status
        RequestIdempotency.update_request_status(
            db, request_id,
            "completed" if success else "failed",
            200 if success else 400,
            response_data,
            None if success else message
        )
        
        if success:
            return {
                "status": "success",
                "message": message,
                "data": response_data,
                "request_id": request_id
            }
        else:
            return {
                "status": "error",
                "message": message,
                "data": response_data,
                "request_id": request_id
            }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Withdrawal failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/operation/deposit")
async def deposit(req: DepositRequest, db: Session = Depends(get_db)):
    """
    Deposit funds to account
    Mostly synchronous but notification is async
    """
    try:
        # Resolve account by phone_number or account_id
        acc_resolved, acc_msg, account = AccountOperations.resolve_account(
            db, req.account_id, req.phone_number
        )
        
        if not acc_resolved:
            raise HTTPException(status_code=404, detail=acc_msg)
        
        account_id = account.account_id
        
        # Generate request ID
        request_id = RequestIdempotency.generate_request_id(
            req.phone_number,
            "deposit",
            req.client_reference
        )
        
        # Check for duplicate
        is_dup, cached_response = RequestIdempotency.is_duplicate_request(db, request_id)
        if is_dup:
            return {
                "status": "success",
                "message": "Duplicate request - cached response",
                "data": cached_response,
                "request_id": request_id
            }
        
        # Create request entry
        RequestIdempotency.create_request_entry(
            db, request_id, account_id, req.phone_number,
            "deposit", {"amount": req.amount}, req.client_ip
        )
        
        # Execute deposit
        success, message, response_data = AccountOperations.deposit(
            db, account_id, req.phone_number,
            Decimal(str(req.amount)), request_id
        )
        
        # Update request status
        RequestIdempotency.update_request_status(
            db, request_id,
            "completed" if success else "failed",
            200 if success else 400,
            response_data,
            None if success else message
        )
        
        # TODO: Queue notification for async sending
        
        if success:
            return {
                "status": "success",
                "message": message,
                "data": response_data,
                "request_id": request_id,
                "notification": "SMS confirmation will be sent"
            }
        else:
            return {
                "status": "error",
                "message": message,
                "data": response_data,
                "request_id": request_id
            }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Deposit failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/operation/balance")
async def check_balance(req: BalanceRequest, db: Session = Depends(get_db)):
    """
    Check account balance (POST endpoint)
    Synchronous operation - returns immediate response
    """
    try:
        # Resolve account by phone_number or account_id
        acc_resolved, acc_msg, account = AccountOperations.resolve_account(
            db, req.account_id, req.phone_number
        )
        
        if not acc_resolved:
            raise HTTPException(status_code=404, detail=acc_msg)
        
        account_id = account.account_id
        
        success, message, response_data = AccountOperations.check_balance(
            db, account_id
        )
        
        if success:
            return {
                "status": "success",
                "message": message,
                "data": response_data
            }
        else:
            raise HTTPException(status_code=404, detail=message)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Balance check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/operation/balance/{account_id}")
async def check_balance_get(account_id: int, db: Session = Depends(get_db)):
    """
    Check account balance (GET endpoint)
    Synchronous operation - returns immediate response
    """
    try:
        success, message, response_data = AccountOperations.check_balance(
            db, account_id
        )
        
        if success:
            return {
                "status": "success",
                "message": message,
                "data": response_data
            }
        else:
            raise HTTPException(status_code=404, detail=message)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Balance check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/operation/transactions/{account_id}")
async def get_transactions(account_id: int, limit: int = 10, db: Session = Depends(get_db)):
    """Get last N transactions (GET endpoint)"""
    try:
        success, message, response_data = AccountOperations.get_last_transactions(
            db, account_id, limit
        )
        
        if success:
            return {
                "status": "success",
                "data": response_data
            }
        else:
            raise HTTPException(status_code=404, detail=message)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transaction query failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/operation/transfer")
async def transfer(req: TransferRequest, db: Session = Depends(get_db)):
    """
    Transfer funds between accounts
    Synchronous operation - returns immediate response
    """
    try:
        # Generate request ID for idempotency
        request_id = RequestIdempotency.generate_request_id(
            req.from_phone_number,
            "transfer",
            req.client_reference
        )
        
        # Check for duplicate request
        is_dup, cached_response = RequestIdempotency.is_duplicate_request(db, request_id)
        if is_dup:
            return {
                "status": "success",
                "message": "Duplicate request - cached response",
                "data": cached_response,
                "request_id": request_id
            }
        
        # Create request entry
        RequestIdempotency.create_request_entry(
            db, request_id, req.from_account_id, req.from_phone_number,
            "transfer", {"amount": req.amount, "to": req.to_phone_number}, req.client_ip
        )
        
        # Execute transfer
        success, message, response_data = AccountOperations.transfer(
            db, req.from_account_id, req.from_phone_number,
            req.to_phone_number, Decimal(str(req.amount)), request_id
        )
        
        # Update request status
        RequestIdempotency.update_request_status(
            db, request_id,
            "completed" if success else "failed",
            200 if success else 400,
            response_data,
            None if success else message
        )
        
        if success:
            return {
                "status": "success",
                "message": message,
                "data": response_data,
                "request_id": request_id
            }
        else:
            return {
                "status": "error",
                "message": message,
                "data": response_data,
                "request_id": request_id
            }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Transfer failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# USSD Gateway
# ============================================

@app.post("/api/v1/ussd")
async def ussd_gateway(req: USSDRequest, db: Session = Depends(get_db)):
    """
    USSD protocol endpoint
    Parses USSD codes and executes operations
    """
    try:
        # Parse USSD input
        parser = USSDParser()
        success, parsed_request, error = parser.parse(req.ussd_input)
        
        if not success:
            formatter = USSDFormatter()
            response = formatter.error_response("0", error)
            return {
                "status": "error",
                "message": error,
                "ussd_response": response
            }
        
        # Get account from phone number
        account = db.query(Account).filter(
            Account.phone_number == parsed_request.phone_number
        ).first()
        
        if not account:
            formatter = USSDFormatter()
            return {
                "status": "error",
                "message": "Account not found. Please create account first.",
                "ussd_response": formatter.error_response(
                    parsed_request.operation,
                    "Account not found"
                )
            }
        
        formatter = USSDFormatter()
        request_id = RequestIdempotency.generate_request_id(
            parsed_request.phone_number,
            parsed_request.operation
        )
        
        # Execute operation
        if parsed_request.operation == "withdraw":
            success, message, data = AccountOperations.withdraw(
                db, account.account_id, parsed_request.phone_number,
                Decimal(str(parsed_request.amount)), request_id
            )
            ussd_response = formatter.success_response(
                "withdraw",
                message,
                data
            ) if success else formatter.error_response("withdraw", message)
            
        elif parsed_request.operation == "deposit":
            success, message, data = AccountOperations.deposit(
                db, account.account_id, parsed_request.phone_number,
                Decimal(str(parsed_request.amount)), request_id
            )
            ussd_response = formatter.pending_response("deposit")
            
        elif parsed_request.operation == "check_balance":
            success, message, data = AccountOperations.check_balance(
                db, account.account_id
            )
            ussd_response = formatter.success_response(
                "check_balance",
                message,
                data
            ) if success else formatter.error_response("check_balance", message)
            
        elif parsed_request.operation == "mini_statement":
            success, message, data = AccountOperations.get_last_transactions(
                db, account.account_id, limit=5
            )
            ussd_response = formatter.success_response(
                "mini_statement",
                message,
                data
            ) if success else formatter.error_response("mini_statement", message)
        
        else:
            ussd_response = formatter.error_response(
                "0", "Unknown operation"
            )
        
        return {
            "status": "success" if success else "error",
            "ussd_response": ussd_response,
            "server_id": server_config.SERVER_ID
        }
        
    except Exception as e:
        logger.error(f"USSD processing failed: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "ussd_response": "*165*0*Service error. Please try again.#"
        }


# ============================================
# Server Discovery & Routing
# ============================================

@app.get("/api/v1/routing/discover/{phone_number}")
async def discover_server(phone_number: str):
    """
    Discover which server a phone number should route to
    Used by clients for server selection
    """
    try:
        routing_info = discovery.route_request(phone_number)
        return {
            "status": "success",
            "routing": routing_info
        }
    except Exception as e:
        logger.error(f"Server discovery failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/hash-ring/status")
async def hash_ring_status():
    """Get hash ring configuration and status"""
    return {
        "status": "success",
        "hash_ring": hash_ring.get_status()
    }


# ============================================
# Gossip Protocol Endpoints
# ============================================

# NOTE: These endpoints will be populated when gossip module is initialized
# For now, they serve as stubs and will be replaced at startup

@app.post("/api/v1/gossip/heartbeat")
async def gossip_heartbeat(request: Request):
    """
    Receive heartbeat from peer server
    Updates peer status and vector clocks
    """
    try:
        payload = await request.json()
        
        # In production, this would update gossip node state
        # For now, return success
        logger.debug(f"Heartbeat received from {payload.get('source_server_id')}")
        
        return {
            "status": "success",
            "message": "Heartbeat received",
            "server_id": server_config.SERVER_ID,
        }
    except Exception as e:
        logger.error(f"Error handling heartbeat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/gossip/sync-state")
async def gossip_sync_state(request: Request):
    """
    Receive state sync (replicated events) from peer
    Applies events received from other servers
    """
    try:
        payload = await request.json()
        source_server = payload.get('source_server_id')
        sync_events = payload.get('sync_events', [])
        
        logger.debug(f"Sync state received from {source_server}: {len(sync_events)} events")
        
        # In production, this would process and apply events
        # For now, return acknowledgement
        
        return {
            "status": "success",
            "message": "State sync received",
            "acked_event_ids": [e.get('event_id') for e in sync_events],
        }
    except Exception as e:
        logger.error(f"Error handling sync state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/gossip/status")
async def gossip_status():
    """Get gossip protocol status"""
    try:
        return {
            "status": "success",
            "server_id": server_config.SERVER_ID,
            "message": "Gossip protocol status endpoint"
        }
    except Exception as e:
        logger.error(f"Error getting gossip status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=server_config.SERVER_HOST,
        port=server_config.SERVER_PORT,
        log_level="info"
    )
