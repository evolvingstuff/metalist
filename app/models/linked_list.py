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