# File 4: replies.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Reply
from ..schemas import ReplyCreate
from datetime import datetime

router = APIRouter(prefix="/reply", tags=["Reply"])

@router.post("/")
def create_reply(reply: ReplyCreate, db: Session = Depends(get_db)):
    db_review = db.query(Review).filter_by(id=reply.review_id).first()
    if not db_review:
        return {"error": "Review not found"}
    
    db_reply = Reply(
        review_id=reply.review_id,
        suggested_text=reply.suggested_text[:500],
        user_edited_text=reply.user_edited_text[:500] if reply.user_edited_text else None,
        status="Draft",
        date_suggested=datetime.utcnow()
    )
    db.add(db_reply)
    db.commit()
    db.refresh(db_reply)
    return db_reply
