# review_saas/app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company
from ..auth import get_current_user  # Make sure this is correctly implemented
from collections import Counter, defaultdict
from datetime import datetime
import re
from typing import List, Dict, Any

router = APIRouter(prefix="/reviews", tags=["reviews"])


# ────────────────────────────────────────────────
# Utilities
# ────────────────────────────────────────────────
def classify_sentiment(rating: int | float | None) -> str:
    if rating is None:
        return "Neutral"
    if rating >= 4:
        return "Positive"
    elif rating == 3:
        return "Neutral"
    else:
        return "Negative"


def extract_keywords(text: str | None) -> List[str]:
    if not text:
        return []
    # Remove punctuation and normalize
    text = re.sub(r'[^\w\s]', '', text.lower())
    words = text.split()
    stopwords = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "has", "have", "he", "in", "is", "it", "its", "of", "on", "that",
        "the", "to", "was", "were", "will", "with", "this", "i", "me", "my"
    }
    return [w for w in words if w not in stopwords and len(w) > 2]


def generate_suggested_reply(sentiment: str) -> str:
    templates = {
        "Positive": [
            "Thank you so much for your kind words! We're thrilled you had a great experience.",
            "We really appreciate your positive feedback — thank you!",
            "Thanks for the wonderful review! It means a lot to us."
        ],
        "Neutral": [
            "Thank you for your feedback. We're always looking to improve.",
            "Thanks for taking the time to share your thoughts."
        ],
        "Negative": [
            "We're truly sorry for the experience you had. Please contact us so we can make this right.",
            "We apologize for falling short. We'd love the chance to improve your experience — please reach out."
        ]
    }
    import random
    return random.choice(templates.get(sentiment, templates["Neutral"]))


def get_review_summary_data(reviews: List[Review]) -> Dict[str, Any]:
    if not reviews:
        return {
            "total_reviews": 0,
            "avg_rating": 0.0,
            "sentiments": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "positive_keywords": [],
            "negative_keywords": [],
            "trend_data": [],
            "reviews": [],
            "company_name": ""
        }

    total_reviews = len(reviews)
    valid_ratings = [r.rating for r in reviews if r.rating is not None]
    avg_rating = round(sum(valid_ratings) / len(valid_ratings), 2) if valid_ratings else 0.0

    sentiments_count = {"Positive": 0, "Neutral": 0, "Negative": 0}
    positive_keywords: List[str] = []
    negative_keywords: List[str] = []
    review_list = []
    monthly_ratings = defaultdict(list)

    for r in reviews:
        sentiment = classify_sentiment(r.rating)
        sentiments_count[sentiment] += 1

        keywords = extract_keywords(r.review_text)
        if sentiment == "Positive":
            positive_keywords.extend(keywords)
        elif sentiment == "Negative":
            negative_keywords.extend(keywords)

        review_list.append({
            "id": r.id,
            "review_text": r.review_text or "",
            "rating": r.rating,
            "reviewer_name": r.reviewer_name or "Anonymous",
            "review_date": r.review_date.isoformat() if r.review_date else None,
            "sentiment": sentiment,
            "suggested_reply": generate_suggested_reply(sentiment)
        })

        if r.review_date:
            month_key = r.review_date.strftime('%Y-%m')
            monthly_ratings[month_key].append(r.rating or 0)

    trend_data = []
    for month in sorted(monthly_ratings.keys()):
        ratings_list = monthly_ratings[month]
        avg = sum(ratings_list) / len(ratings_list) if ratings_list else 0
        trend_data.append({
            "month": month,
            "avg_rating": round(avg, 2),
            "count": len(ratings_list)
        })

    return {
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "sentiments": sentiments_count,
        "positive_keywords": [k for k, _ in Counter(positive_keywords).most_common(5)],
        "negative_keywords": [k for k, _ in Counter(negative_keywords).most_common(5)],
        "trend_data": trend_data,
        "reviews": sorted(review_list, key=lambda x: x.get("review_date") or "0000-00-00", reverse=True),
        "company_name": ""  # will be filled in endpoint
    }


# ────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────

@router.get("/")
def list_all_reviews(db: Session = Depends(get_db)):
    return db.query(Review).all()


@router.get("/summary/{company_id}")
def reviews_summary(
    company_id: int,
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    
    data = get_review_summary_data(reviews)
    data["company_name"] = company.name
    return data


@router.get("/my-companies")
def get_my_companies(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns list of companies owned by the authenticated user
    Used to populate company selector in dashboard
    """
    companies = db.query(Company).filter(Company.user_id == current_user.id).all()
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "place_id": c.place_id,
            "city": c.city,
            "added_at": c.added_at.isoformat() if c.added_at else None
        }
        for c in sorted(companies, key=lambda x: x.name or "")
    ]
