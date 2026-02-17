# app/routes/reply.py

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import sessionmaker
from ..db import engine
from ..models import Reply, Review
from ..services.replies import suggest

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
router = APIRouter(prefix="/reply", tags=["reply"])


@router.post("/{review_id}")
def save_reply(review_id: int, edited_text: str | None = None, mark_sent: bool = False):
    with SessionLocal() as s:
        rv = s.get(Review, review_id)
        if not rv:
            raise HTTPException(status_code=404, detail="Review not found")

        rep = s.query(Reply).filter(Reply.review_id == review_id).first()
        if not rep:
            rep = Reply(review_id=review_id, suggested_text=suggest(rv.text, rv.sentiment))
            s.add(rep)

        if edited_text is not None:
            rep.edited_text = (edited_text or "")[:500]

        if mark_sent:
            rep.status = "Sent"

        s.commit()
        s.refresh(rep)
        return {"id": rep.id, "status": rep.status}
