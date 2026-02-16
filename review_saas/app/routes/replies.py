# review_saas/app/routes/replies.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import SuggestedReply, Review, Company
from ..services.emailer import send_email

router = APIRouter(prefix="/replies", tags=["replies"])

@router.get("/{review_id}")
async def get_reply(review_id: int, db: Session = Depends(get_db)):
    sr = db.query(SuggestedReply).filter(SuggestedReply.review_id == review_id).first()
    if not sr:
        raise HTTPException(status_code=404, detail="Not found")
    return {"suggested_text": sr.suggested_text, "user_edited_text": sr.user_edited_text, "status": sr.status}

@router.post("/{review_id}")
async def update_reply(review_id: int, text: str, db: Session = Depends(get_db)):
    if len(text) > 500:
        raise HTTPException(status_code=400, detail="Max 500 chars")
    sr = db.query(SuggestedReply).filter(SuggestedReply.review_id == review_id).first()
    if not sr:
        raise HTTPException(status_code=404, detail="Not found")
    sr.user_edited_text = text
    db.commit()
    return {"message": "Updated"}

@router.post("/send/{review_id}")
async def send_reply(review_id: int, to: str | None = None, db: Session = Depends(get_db)):
    sr = db.query(SuggestedReply).filter(SuggestedReply.review_id == review_id).first()
    rv = db.query(Review).get(review_id)
    if not sr or not rv:
        raise HTTPException(status_code=404, detail="Not found")

    # Optional: email integration — default to owner email if 'to' not provided
    cmp = db.query(Company).get(rv.company_id)
    recipient = to or (cmp.owner.email if cmp and cmp.owner else None)
    if recipient:
        body = sr.user_edited_text or sr.suggested_text or "Thank you for your feedback."
        send_email(recipient, "Reply to Review", body)

    sr.status = "Sent"
    from datetime import datetime
    sr.sent_at = datetime.utcnow()
    db.commit()
    return {"message": "Marked as sent"}
