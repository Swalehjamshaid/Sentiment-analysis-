# File 3: sentiment.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review
from textblob import TextBlob

router = APIRouter(prefix="/sentiment", tags=["Sentiment"])

@router.post("/analyze/{review_id}")
def analyze_sentiment(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).filter_by(id=review_id).first()
    if not review:
        return {"error": "Review not found"}
    
    text = review.text
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity
    if polarity > 0.1:
        sentiment = "Positive"
    elif polarity < -0.1:
        sentiment = "Negative"
    else:
        sentiment = "Neutral"
    
    review.sentiment_category = sentiment
    review.sentiment_score = polarity
    db.commit()
    return {"review_id": review.id, "sentiment": sentiment, "score": polarity}
