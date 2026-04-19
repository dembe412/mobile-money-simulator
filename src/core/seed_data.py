"""
Idempotent data seeding functions for initializing empty tables
Ensures that ServerStatus and EventReplicationState tables are properly initialized
without duplicating data if seeding is run multiple times.
"""
import logging
from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.models import ServerStatus, EventReplicationState, Event
from config.settings import server_config, replication_config, app_config

logger = logging.getLogger(__name__)


def seed_server_status(db: Session, server_id: str = None) -> Dict[str, Any]:
    """
    Create ServerStatus entry for this server if it doesn't exist.
    Idempotent - safe to call multiple times.
    
    Args:
        db: Database session
        server_id: Server ID (defaults to config.SERVER_ID)
        
    Returns:
        Dictionary with seeding results {"seeded": bool, "count": int, "server_id": str}
    """
    server_id = server_id or server_config.SERVER_ID
    
    try:
        # Check if ServerStatus already exists for this server
        existing = db.query(ServerStatus).filter(
            ServerStatus.server_id == server_id
        ).first()
        
        if existing:
            logger.info(f"ServerStatus already exists for server '{server_id}'. Skipping seed.")
            return {
                "seeded": False,
                "count": 0,
                "server_id": server_id,
                "reason": "Already exists"
            }
        
        # Create ServerStatus entry
        server_status = ServerStatus(
            server_id=server_id,
            server_name=server_config.SERVER_NAME,
            host=server_config.SERVER_HOST,
            port=server_config.SERVER_PORT,
            status="online",
            last_heartbeat=datetime.utcnow(),
            last_sync=datetime.utcnow(),
            sync_lag_seconds=0,
            total_transactions=0,
            error_count=0,
            peer_vector_clock={server_id: 0},
            sync_position=0,
            ops_behind=0,
            pending_events_count=0,
        )
        
        db.add(server_status)
        db.commit()
        
        logger.info(f"Seeded ServerStatus for server '{server_id}'")
        
        return {
            "seeded": True,
            "count": 1,
            "server_id": server_id,
        }
        
    except IntegrityError as e:
        db.rollback()
        logger.debug(f"ServerStatus seeding integrity error (likely duplicate): {e}")
        return {
            "seeded": False,
            "count": 0,
            "server_id": server_id,
            "reason": "Integrity error (likely already exists)"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding ServerStatus: {e}")
        raise


def seed_event_replication_state(db: Session, event_ids: List[str] = None) -> Dict[str, Any]:
    """
    Create EventReplicationState entries for pending events if they don't exist.
    Idempotent - safe to call multiple times.
    
    Creates replication state entries for all pending/applied events that don't have
    replication state records yet. This enables proper event replication tracking.
    
    Args:
        db: Database session
        event_ids: Specific event IDs to seed (defaults to all untracked events)
        
    Returns:
        Dictionary with seeding results {"seeded": bool, "count": int}
    """
    try:
        # Get list of events to seed
        if event_ids:
            # Seed specific events
            events_to_seed = db.query(Event).filter(
                Event.event_id.in_(event_ids)
            ).all()
        else:
            # Get all events without replication state
            events_with_replication = db.query(EventReplicationState.event_id).distinct()
            existing_event_ids = [row[0] for row in events_with_replication]
            
            events_to_seed = db.query(Event).filter(
                Event.event_id.notin_(existing_event_ids) if existing_event_ids else True
            ).all()
        
        if not events_to_seed:
            logger.info("No events to seed EventReplicationState. All events already tracked.")
            return {
                "seeded": False,
                "count": 0,
                "reason": "No untracked events found"
            }
        
        seeded_count = 0
        
        # Standard server IDs for replication tracking
        for event in events_to_seed:
            for server_id in ["server_1", "server_2", "server_3"]:
                # Check if replication state already exists
                existing = db.query(EventReplicationState).filter(
                    EventReplicationState.event_id == event.event_id,
                    EventReplicationState.server_id == server_id
                ).first()
                
                if not existing:
                    replication_state = EventReplicationState(
                        event_id=event.event_id,
                        server_id=server_id,
                        acked=False,
                        acked_at=None,
                    )
                    db.add(replication_state)
                    seeded_count += 1
        
        if seeded_count > 0:
            db.commit()
            logger.info(f"Seeded {seeded_count} EventReplicationState entries")
        
        return {
            "seeded": seeded_count > 0,
            "count": seeded_count,
        }
        
    except IntegrityError as e:
        db.rollback()
        logger.debug(f"EventReplicationState seeding integrity error: {e}")
        return {
            "seeded": False,
            "count": 0,
            "reason": "Integrity error (likely already exists)"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding EventReplicationState: {e}")
        raise


def run_all_seeds(db: Session) -> Dict[str, Any]:
    """
    Orchestrate all seeding operations.
    Idempotent - safe to call multiple times.
    
    Args:
        db: Database session
        
    Returns:
        Dictionary with combined seeding results
    """
    logger.info(f"Starting data seeding for environment '{app_config.APP_ENV}'")
    
    results = {
        "environment": app_config.APP_ENV,
        "timestamp": datetime.utcnow().isoformat(),
        "seeds": {}
    }
    
    # Seed ServerStatus
    server_status_result = seed_server_status(db)
    results["seeds"]["server_status"] = server_status_result
    
    # Seed EventReplicationState
    event_replication_result = seed_event_replication_state(db)
    results["seeds"]["event_replication_state"] = event_replication_result
    
    # Summary
    total_seeded = sum(1 for seed in results["seeds"].values() if seed.get("seeded", False))
    logger.info(f"Seeding completed. {total_seeded} seed operations successful.")
    
    return results
