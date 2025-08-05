import uuid
from sqlalchemy.orm import Session
from app.models.database import SyncState


def generate_update_event(db: Session) -> str:
    """Generate a new update UUID and store it in sync_state table.
    
    This should be called whenever any change occurs to the notes database
    (create, edit, delete, move operations).
    
    Returns:
        str: The new update UUID
    """
    new_uuid = str(uuid.uuid4())
    
    # Check if sync_state table has any records
    sync_state = db.query(SyncState).first()
    
    if sync_state is None:
        # Create initial sync state record
        sync_state = SyncState(last_update_uuid=new_uuid)
        db.add(sync_state)
    else:
        # Update existing record
        sync_state.last_update_uuid = new_uuid
    
    db.commit()
    return new_uuid


def get_current_update_uuid(db: Session) -> str:
    """Get the current update UUID from the sync_state table.
    
    Returns:
        str: The current update UUID, or a new one if none exists
    """
    sync_state = db.query(SyncState).first()
    
    if sync_state is None:
        # Initialize sync state if it doesn't exist
        return generate_update_event(db)
    
    return sync_state.last_update_uuid


def check_needs_update(db: Session, client_last_known_uuid: str) -> tuple[bool, str]:
    """Check if the client needs to refresh based on their last known UUID.
    
    Args:
        db: Database session
        client_last_known_uuid: The last update UUID the client knows about
    
    Returns:
        tuple: (needs_update: bool, current_uuid: str)
    """
    current_uuid = get_current_update_uuid(db)
    needs_update = client_last_known_uuid != current_uuid
    
    return needs_update, current_uuid