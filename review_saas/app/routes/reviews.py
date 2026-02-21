# File: app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company
from collections import Counter, defaultdict
from datetime import datetime
import re
import os
from typing import List, Dict, Any
import googlemaps
import random

router = APIRouter(prefix="/reviews", tags=["reviews"])

# ─── Google Places Client ───────────────────────────────────────────────────
api_key = os.getenv("GOOGLE_PLACES_API_KEY")
if not api_key:
    raise RuntimeError("Google Places API key not set in environment")
gmaps = googlemaps.Client(key=api_key)


def fetch_and_save_reviews(company: Company, db: Session, max_reviews: int = 5) -> int:
    """Fetch reviews from Google Places API and save new ones (slow operation)"""
    if not company.place_id:
        return 0

    try:
        place_result = gmaps.place(
            place_id=company.place_id,
            fields=["reviews", "rating", "user_ratings_total"]
        )
        result = place_result.get("result", {})
        api_reviews = result.get("reviews", [])[:max_reviews]

        added_count = 0
        for rev in api_reviews:
            review_time = rev.get("time")
            review_date = datetime.fromtimestamp(review_time) if review_time else None

            existing = db.query(Review).filter(
                Review.company_id == company.id,
                Review.text == rev.get("text", ""),
                Review.rating == rev.get("rating"),
                Review.review_date == review_date
            ).first()

            if existing:
                continue

            new_review = Review(
                company_id=company.id,
                text=rev.get("text", ""),
                rating=rev.get("rating"),
                reviewer_name=rev.get("author_name", "Anonymous"),
                review_date=review_date,
                fetch_at=datetime.utcnow()
            )
            db.add(new_review)
            added_count += 1

        # Update company metadata
        new_rating = result.get("rating")
        new_total = result.get("user_ratings_total")

        if added_count > 0 or new_rating is not None or new_total is not None:
            if new_rating is not None:
                company.google_rating = new_rating
            if new_total is not None:
                company.user_ratings_total = new_total
            db.commit()

        return added_count

    except googlemaps.exceptions.ApiError as e:
        print(f"Google Places API error: {e}")
        return 0
    except Exception as e:
        print(f"Unexpected error during fetch: {e}")
        return 0


# ─── Sentiment & Reply Helpers ──────────────────────────────────────────────
def classify_sentiment(rating: float | None) -> str:
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
    return random.choice(templates.get(sentiment, templates["Neutral"]))


# ─── Enhanced Dashboard Summary with AI Recommendations ───────────────────
def get_review_summary_data(reviews: List[Review], company: Company) -> Dict[str, Any]:
    google_rating = getattr(company, "google_rating", None)
    google_total_ratings = getattr(company, "user_ratings_total", None)

    if not reviews:
        return {
            "company_name": company.name or "Unnamed Company",
            "google_rating": google_rating,
            "google_total_ratings": google_total_ratings,
            "total_reviews": 0,
            "avg_rating": 0.0,
            "sentiments": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "positive_keywords": [],
            "negative_keywords": [],
            "trend_data": [],
            "weak_areas": [],
            "strength_areas": [],
            "ai_recommendations": [],
            "risk_score": 0,
            "reviews": []
        }

    total_reviews = len(reviews)
    valid_ratings = [r.rating for r in reviews if r.rating is not None]
    avg_rating = round(sum(valid_ratings) / len(valid_ratings), 2) if valid_ratings else 0.0

    sentiments_count = {"Positive": 0, "Neutral": 0, "Negative": 0}
    positive_keywords = []
    negative_keywords = []
    monthly_ratings = defaultdict(list)
    review_list = []

    for r in reviews:
        sentiment = classify_sentiment(r.rating)
        sentiments_count[sentiment] += 1

        keywords = extract_keywords(r.text)
        if sentiment == "Positive":
            positive_keywords.extend(keywords)
        elif sentiment == "Negative":
            negative_keywords.extend(keywords)

        review_list.append({
            "id": r.id,
            "review_text": r.text or "",
            "rating": r.rating,
            "reviewer_name": r.reviewer_name or "Anonymous",
            "review_date": r.review_date.isoformat() if r.review_date else None,
            "sentiment": sentiment,
            "suggested_reply": generate_suggested_reply(sentiment)
        })

        if r.review_date:
            month_key = r.review_date.strftime('%Y-%m')
            monthly_ratings[month_key].append(r.rating or 0.0)

    # ─── Trend Graph Data ───
    trend_data = []
    for month in sorted(monthly_ratings.keys()):
        ratings_list = monthly_ratings[month]
        avg = sum(ratings_list) / len(ratings_list) if ratings_list else 0
        trend_data.append({
            "month": month,
            "avg_rating": round(avg, 2),
            "count": len(ratings_list)
        })

    # ─── Keyword Analysis ───
    positive_counter = Counter(positive_keywords)
    negative_counter = Counter(negative_keywords)

    top_positive = positive_counter.most_common(8)
    top_negative = negative_counter.most_common(8)

    # ─── Weak / Strength Areas ───
    weak_areas = [{"keyword": k, "mentions": v} for k, v in top_negative]
    strength_areas = [{"keyword": k, "mentions": v} for k, v in top_positive]

    # ─── Risk Score ───
    negative_ratio = sentiments_count["Negative"] / total_reviews
    risk_score = round(negative_ratio * 100, 2)

    # ─── AI Recommendations ───
    ai_recommendations = []
    for keyword, count in top_negative[:5]:
        recommendation = {
            "weak_area": keyword,
            "issue_mentions": count,
            "priority": "High" if count > 3 else "Medium",
            "recommended_action": f"Investigate root cause of '{keyword}' complaints and implement corrective actions.",
            "expected_outcome": "Improved customer satisfaction and reduction in negative sentiment."
        }
        ai_recommendations.append(recommendation)

    return {
        "company_name": company.name or "Unnamed Company",
        "google_rating": google_rating,
        "google_total_ratings": google_total_ratings,
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "sentiments": sentiments_count,
        "positive_keywords": [k for k, _ in top_positive],
        "negative_keywords": [k for k, _ in top_negative],
        "trend_data": trend_data,
        "weak_areas": weak_areas,
        "strength_areas": strength_areas,
        "ai_recommendations": ai_recommendations,
        "risk_score": risk_score,
        "reviews": sorted(
            review_list,
            key=lambda x: datetime.fromisoformat(x["review_date"]) if x["review_date"] else datetime.min,
            reverse=True
        )[:15]
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.post("/fetch/{company_id}")
def fetch_reviews(
    company_id: int,
    db: Session = Depends(get_db)
):
    """Manually trigger full review fetch from Google"""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    added = fetch_and_save_reviews(company, db)
    return {"message": "Fresh fetch completed", "new_reviews_added": added}


@router.get("/summary/{company_id}")
def reviews_summary(
    company_id: int,
    refresh: bool = Query(False, description="If true, fetch fresh reviews from Google (may take 5–20 seconds)"),
    db: Session = Depends(get_db)
):
    """Fast dashboard summary — only fetches from Google if ?refresh=true"""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    if refresh:
        fetch_and_save_reviews(company, db)

    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    return get_review_summary_data(reviews, company)


@router.get("/my-companies")
def get_my_companies(db: Session = Depends(get_db)):
    """List companies for dashboard dropdown (fast)"""
    companies = db.query(Company).all()  # TODO: later → .filter(Company.owner_id == current_user.id)
    return [
        {
            "id": c.id,
            "name": c.name or "Unnamed",
            "place_id": c.place_id,
            "city": getattr(c, "city", "N/A")
        }
        for c in sorted(companies, key=lambda x: (x.name or "").lower())
    ]
