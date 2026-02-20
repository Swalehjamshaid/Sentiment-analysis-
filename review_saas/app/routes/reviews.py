# review_saas/app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company
from collections import Counter, defaultdict
from datetime import datetime
import re
from typing import List, Dict

router = APIRouter(prefix="/reviews", tags=["reviews"])


# =========================
# Pure Python Utilities
# =========================
def classify_sentiment(rating: int | float) -> str:
    """Simple rule-based sentiment classification based on star rating"""
    if rating >= 4:
        return "Positive"
    elif rating == 3:
        return "Neutral"
    else:
        return "Negative"


def extract_keywords(text: str) -> List[str]:
    """Basic keyword extraction: lowercase, remove punctuation, filter stopwords & short words"""
    if not text:
        return []

    text = re.sub(r'[^\w\s]', '', text.lower())
    words = text.split()

    stopwords = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "has", "have", "he", "in", "is", "it", "its", "of", "on", "that",
        "the", "to", "was", "were", "will", "with", "this", "i", "me", "my"
    }

    keywords = [w for w in words if w not in stopwords and len(w) > 2]
    return keywords


def generate_suggested_reply(sentiment: str) -> str:
    """Template-based reply generator (no external AI required)"""
    templates = {
        "Positive": [
            "Thank you so much for your kind words! We're thrilled you had a great experience.",
            "We really appreciate your positive feedback — thank you!",
            "Thanks for the wonderful review! It means a lot to us.",
            "We're so glad you enjoyed it — thank you for choosing us!"
        ],
        "Neutral": [
            "Thank you for your feedback. We're always looking to improve.",
            "Thanks for taking the time to share your thoughts.",
            "We appreciate your honest review and will use it to get better."
        ],
        "Negative": [
            "We're truly sorry for the experience you had. Please contact us so we can make this right.",
            "We apologize for falling short. We'd love the chance to improve your experience — please reach out.",
            "We're sorry to hear this wasn't up to our standards. Please let us know how we can help."
        ]
    }
    import random
    return random.choice(templates.get(sentiment, templates["Neutral"]))


def get_review_summary_data(reviews: List[Review]) -> Dict:
    """Compute summary statistics + trend data from reviews"""
    if not reviews:
        return {
            "total_reviews": 0,
            "avg_rating": 0.0,
            "sentiments": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "positive_keywords": [],
            "negative_keywords": [],
            "trend_data": [],
            "reviews": []
        }

    total_reviews = len(reviews)
    total_rating = sum(r.rating for r in reviews)
    avg_rating = round(total_rating / total_reviews, 2)

    sentiments_count = {"Positive": 0, "Neutral": 0, "Negative": 0}
    positive_keywords = []
    negative_keywords = []
    review_list = []

    # For trend: group by month
    monthly_ratings = defaultdict(list)

    for r in reviews:
        sentiment = classify_sentiment(r.rating)
        sentiments_count[sentiment] += 1

        keywords = extract_keywords(r.review_text or "")
        if sentiment == "Positive":
            positive_keywords.extend(keywords)
        elif sentiment == "Negative":
            negative_keywords.extend(keywords)

        suggested_reply = generate_suggested_reply(sentiment)

        review_list.append({
            "id": r.id,
            "review_text": r.review_text or "",
            "rating": r.rating,
            "reviewer_name": r.reviewer_name or "Anonymous",
            "review_date": r.review_date.isoformat() if r.review_date else None,
            "sentiment": sentiment,
            "suggested_reply": suggested_reply
        })

        # Trend data preparation
        if r.review_date:
            month_key = r.review_date.strftime('%Y-%m')
            monthly_ratings[month_key].append(r.rating)

    # Build sorted trend data
    trend_data = []
    for month in sorted(monthly_ratings.keys()):
        ratings_list = monthly_ratings[month]
        avg = sum(ratings_list) / len(ratings_list)
        trend_data.append({
            "month": month,
            "avg_rating": round(avg, 2),
            "count": len(ratings_list)
        })

    top_positive = [k for k, _ in Counter(positive_keywords).most_common(5)]
    top_negative = [k for k, _ in Counter(negative_keywords).most_common(5)]

    return {
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "sentiments": sentiments_count,
        "positive_keywords": top_positive,
        "negative_keywords": top_negative,
        "trend_data": trend_data,
        "reviews": sorted(review_list, key=lambda x: x["review_date"] or "0000-00-00", reverse=True)
    }


# =========================
# API Endpoints
# =========================
@router.get("/")
def list_all_reviews(db: Session = Depends(get_db)):
    return db.query(Review).all()


@router.get("/summary/{company_id}")
def reviews_summary(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    return get_review_summary_data(reviews)
