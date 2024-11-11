from typing import Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException

class LinkedListManager:
    @staticmethod
    def get_head(db: Session, model_class) -> Optional[str]:
        """Get the ID of the first item in the list"""
        head = db.query(model_class).filter(model_class.prev_id == None).first()
        return head.id if head else None

    @staticmethod
    def get_tail(db: Session, model_class) -> Optional[str]:
        """Get the ID of the last item in the list"""
        tail = db.query(model_class).filter(model_class.next_id == None).first()
        return tail.id if tail else None

    @staticmethod
    def get_ordered_list(db: Session, model_class) -> List:
        """Get all items in linked list order"""
        items = []
        current = db.query(model_class).filter(model_class.prev_id == None).first()
        
        while current:
            items.append(current)
            current = db.query(model_class).filter(model_class.id == current.next_id).first()
        
        return items

    @staticmethod
    def insert_after(db: Session, model_class, item_id: str, target_id: Optional[str] = None):
        """Insert item after target (or at start if target is None)"""
        item = db.query(model_class).get(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # Remove from current position
        if item.prev_id:
            prev_item = db.query(model_class).get(item.prev_id)
            prev_item.next_id = item.next_id
        if item.next_id:
            next_item = db.query(model_class).get(item.next_id)
            next_item.prev_id = item.prev_id

        if target_id is None:
            # Insert at start
            current_head = db.query(model_class).filter(model_class.prev_id == None).first()
            if current_head:
                current_head.prev_id = item_id
                item.next_id = current_head.id
            item.prev_id = None
        else:
            # Insert after target
            target = db.query(model_class).get(target_id)
            if not target:
                raise HTTPException(status_code=404, detail="Target not found")
            
            item.next_id = target.next_id
            item.prev_id = target_id
            if target.next_id:
                next_item = db.query(model_class).get(target.next_id)
                next_item.prev_id = item_id
            target.next_id = item_id

        db.commit()

    @staticmethod
    def insert_before(db: Session, model_class, item_id: str, target_id: Optional[str] = None):
        """Insert item before target (or at end if target is None)"""
        item = db.query(model_class).get(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # Remove from current position
        if item.prev_id:
            prev_item = db.query(model_class).get(item.prev_id)
            prev_item.next_id = item.next_id
        if item.next_id:
            next_item = db.query(model_class).get(item.next_id)
            next_item.prev_id = item.prev_id

        if target_id is None:
            # Insert at end
            current_tail = db.query(model_class).filter(model_class.next_id == None).first()
            if current_tail:
                current_tail.next_id = item_id
                item.prev_id = current_tail.id
            item.next_id = None
        else:
            # Insert before target
            target = db.query(model_class).get(target_id)
            if not target:
                raise HTTPException(status_code=404, detail="Target not found")
            
            item.prev_id = target.prev_id
            item.next_id = target_id
            if target.prev_id:
                prev_item = db.query(model_class).get(target.prev_id)
                prev_item.next_id = item_id
            target.prev_id = item_id

        db.commit()