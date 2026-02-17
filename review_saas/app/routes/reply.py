# app/routes/reply.py

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import sessionmaker
from ..db import engine  # Make sure this matches your actual db.py location
from ..models import Reply, Review
from ..services.replies import suggest  # Correct import

# Create a SQLAlchemy session factory
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Define FastAPI router
router = APIRouter(prefix="/reply", tags=["reply"])


@router.post("/{review_id}")
def save_reply(review_id: int, edited_text: str | None = None, mark_sent: bool = False):
    """
    Save a suggested reply for a review. 

    Parameters:
        review_id (int): ID of the review to reply to.
        edited_text (str | None): Optional edited text for the reply.
        mark_sent (bool): If True, marks the reply as "Sent".

    Returns:
        dict: Contains the reply ID and current status.
    """
    with SessionLocal() as s:
        # Fetch the review
        rv = s.get(Review, review_id)
        if not rv:
            raise HTTPException(status_code=404, detail="Review not found")

        # Check if a reply already exists
        rep = s.query(Reply).filter(Reply.review_id == review_id).first()
        if not rep:
            # Create a new reply with suggested text
            rep = Reply(review_id=review_id, suggested_text=suggest(rv.text, rv.sentiment))
            s.add(rep)

        # Update edited text if provided
        if edited_text is not None:
            rep.edited_text = (edited_text or "")[:500]

        # Mark the reply as sent if requested
        if mark_sent:
            rep.status = "Sent"

        # Commit changes and refresh
        s.commit()
        s.refresh(rep)

        return {"id": rep.id, "status": rep.status}
