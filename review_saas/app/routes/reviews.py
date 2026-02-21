# File: review_saas/app/routes/reviews.py

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
import re
import os
import logging
import googlemaps

# ─────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────
logger = logging.getLogger("reviews")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/reviews", tags=["reviews"])

# ─────────────────────────────────────────────────────────────
# Google Maps API Client
# ─────────────────────────────────────────────────────────────
api_key = os.getenv("GOOGLE_PLACES_API_KEY")
if not api_key:
    logger.critical("Google Places API Key not set!")
    raise RuntimeError("Google API key missing")

gmaps = googlemaps.Client(key=api_key)

# ─────────────────────────────────────────────────────────────
# Default Reference Date
# ─────────────────────────────────────────────────────────────
DEFAULT_DATE_FROM = datetime.now(timezone.utc) - timedelta(days=180)

# ─────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────

def classify_sentiment(rating: float | None) -> str:
    if rating is None:
        return "Neutral"
    if rating >= 4:
        return "Positive"
    elif rating == 3:
        return "Neutral"
    return "Negative"

def extract_keywords(text: str | None) -> List[str]:
    if not text:
        return []
    text = re.sub(r"[^\w\s]", "", text.lower())
    stopwords = {"a","an","and","are","as","at","be","by","for","from",
                 "the","this","is","it","to","with","was","of","in","on"}
    return [w for w in text.split() if w not in stopwords and len(w) > 2]

# Map keywords to suggested actions
ACTION_MAP: Dict[str, str] = {
    "wait": "Optimize peak-hour staffing to reduce waiting times.",
    "service": "Train staff to improve customer service.",
    "price": "Review pricing strategy and competitor comparison.",
    "clean": "Increase cleanliness checks and janitorial frequency.",
    "quality": "Audit product supply chain for defects."
}

def _action_for_keyword(keyword: str) -> str:
    for k, action in ACTION_MAP.items():
        if k in keyword:
            return action
    return "Conduct root-cause analysis and monitor sentiment trends."

def _parse_review_date(r) -> datetime:
    """Ensure review_date is datetime with timezone."""
    if not r.review_date:
        return None
    if isinstance(r.review_date, datetime):
        return r.review_date.astimezone(timezone.utc)
    # If it's a date object
    return datetime.combine(r.review_date, datetime.min.time(), tzinfo=timezone.utc)

def _get_date_window() -> tuple[datetime, datetime]:
    start_date = os.getenv("REVIEWS_DATE_FROM")
    end_date = os.getenv("REVIEWS_DATE_TO")
    try:
        start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc) if start_date else DEFAULT_DATE_FROM
    except Exception:
        start = DEFAULT_DATE_FROM
    try:
        end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) if end_date else datetime.now(timezone.utc)
    except Exception:
        end = datetime.now(timezone.utc)
    return start, end

# ─────────────────────────────────────────────────────────────
# Fetch reviews from Google API and store
# ─────────────────────────────────────────────────────────────
def fetch_and_save_reviews(company: Company, db: Session, max_reviews: int = 50) -> int:
    if not company.place_id:
        return 0
    try:
        result = gmaps.place(place_id=company.place_id, fields=["reviews","rating","user_ratings_total"]).get("result",{})
        reviews_data = result.get("reviews", [])[:max_reviews]
        added_count = 0
        for rev in reviews_data:
            rev_time = rev.get("time")
            review_date = datetime.fromtimestamp(rev_time, tz=timezone.utc) if rev_time else None
            exists = db.query(Review).filter(
                Review.company_id==company.id,
                Review.text==rev.get("text",""),
                Review.rating==rev.get("rating"),
                Review.review_date==review_date
            ).first()
            if exists: continue
            db.add(Review(
                company_id=company.id,
                text=rev.get("text",""),
                rating=rev.get("rating"),
                reviewer_name=rev.get("author_name","Anonymous"),
                review_date=review_date,
                fetch_at=datetime.now(timezone.utc)
            ))
            added_count += 1
        # Update company rating
        if "rating" in result: company.google_rating = result["rating"]
        if "user_ratings_total" in result: company.user_ratings_total = result["user_ratings_total"]
        if added_count > 0: db.commit()
        return added_count
    except Exception as e:
        logger.error(f"Error fetching reviews for company {company.id}: {e}")
        return 0

# ─────────────────────────────────────────────────────────────
# Core Analysis Function
# ─────────────────────────────────────────────────────────────
def get_review_summary_data(reviews: List[Review], company: Company) -> Dict[str, Any]:
    start_date, end_date = _get_date_window()
    
    windowed_reviews = [r for r in reviews if (_parse_review_date(r) and start_date <= _parse_review_date(r) <= end_date)]
    if not windowed_reviews:
        return {"company_name": company.name, "total_reviews": 0, "avg_rating": 0, "sentiments": {}, "reviews": [], "ai_recommendations": []}

    # Basic metrics
    total_reviews = len(windowed_reviews)
    ratings = [r.rating for r in windowed_reviews if r.rating is not None]
    avg_rating = round(sum(ratings)/len(ratings), 2) if ratings else 0.0

    # Sentiment breakdown
    sentiments = {"Positive":0,"Neutral":0,"Negative":0}
    pos_keywords, neg_keywords = [], []
    trend_data = defaultdict(list)
    reviews_list = []

    for r in windowed_reviews:
        r_dt = _parse_review_date(r)
        sentiment = classify_sentiment(r.rating)
        sentiments[sentiment] += 1
        kws = extract_keywords(r.text)
        if sentiment=="Positive": pos_keywords.extend(kws)
        if sentiment=="Negative": neg_keywords.extend(kws)
        trend_data[r_dt.strftime("%Y-%m")].append(r.rating or 0)
        reviews_list.append({
            "id": r.id,
            "review_text": r.text or "",
            "rating": r.rating,
            "reviewer_name": r.reviewer_name or "Anonymous",
            "review_date": r_dt.isoformat(),
            "sentiment": sentiment,
            "suggested_reply": "Thank you for your feedback. We value your input."
        })

    # Trend analysis per month
    trend_data_list = [{"month": m, "avg_rating": round(sum(v)/len(v),2), "count":len(v)} for m,v in sorted(trend_data.items())]

    # AI-style recommendations for negative trends
    top_neg = Counter(neg_keywords).most_common(5)
    ai_recs = [{
        "weak_area": k,
        "issue_mentions": v,
        "priority": "High" if v>2 else "Medium",
        "recommended_action": _action_for_keyword(k),
        "expected_outcome": "Improved customer satisfaction and reduced churn."
    } for k,v in top_neg]

    # Risk score
    risk_score = round((sentiments["Negative"]/total_reviews)*100, 2)

    return {
        "company_name": company.name,
        "google_rating": getattr(company,"google_rating",0),
        "google_total_ratings": getattr(company,"user_ratings_total",0),
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "sentiments": sentiments,
        "positive_keywords": [k for k,_ in Counter(pos_keywords).most_common(8)],
        "negative_keywords": top_neg,
        "trend_data": trend_data_list,
        "weak_areas": [{"keyword": k, "mentions": v} for k,v in top_neg],
        "strength_areas": [{"keyword": k, "mentions": v} for k,v in Counter(pos_keywords).most_common(8)],
        "ai_recommendations": ai_recs,
        "risk_score": risk_score,
        "reviews": sorted(reviews_list, key=lambda x: x["review_date"], reverse=True)[:15]
    }

# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────
@router.get("/summary/{company_id}")
def reviews_summary(company_id: int, refresh: bool = False, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id==company_id).first()
    if not company: raise HTTPException(status_code=404, detail="Company not found")
    if refresh: fetch_and_save_reviews(company, db)
    reviews = db.query(Review).filter(Review.company_id==company_id).all()
    return get_review_summary_data(reviews, company)

@router.get("/my-companies")
def get_my_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).all()
    return [{"id": c.id, "name": c.name, "city": getattr(c,"city","N/A")} for c in companies]
