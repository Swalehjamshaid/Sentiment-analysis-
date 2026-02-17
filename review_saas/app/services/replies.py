# app/routes/reply.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db

router = APIRouter(
    prefix="/reply",
    tags=["Reply"]
)

def suggest(review_text: str, sentiment: str | None = None) -> str:
    """
    Suggests a reply based on review text and sentiment.
    """
    t = (review_text or "").lower()
    s = (sentiment or "").lower()

    if s == 'negative' or any(w in t for w in ['bad', 'terrible', 'awful', 'worst', 'poor']):
        return "We’re sorry about your experience. Please contact support@example.com so we can help."[:500]

    if s == 'positive' or any(w in t for w in ['great', 'excellent', 'love', 'amazing', 'best']):
        return "Thank you for your kind words! We truly appreciate your feedback."[:500]

    return "Thanks for sharing your thoughts. We value your feedback and will keep improving."[:500]

@router.post("/suggest")
def get_suggested_reply(review_text: str, sentiment: str | None = None, db: Session = Depends(get_db)):
    """
    Endpoint to get suggested reply for a review.
    """
    reply_message = suggest(review_text, sentiment)
    # Here you can save reply_message in DB if needed
    return {"suggested_reply": reply_message}
