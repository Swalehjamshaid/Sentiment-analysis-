# File: app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import re
import os
import random
import logging
from typing import List, Dict, Any, Tuple
import googlemaps

# ──────────────────────────────────────────────────────────────────────────────
# GLOBAL CONFIGURATION & LOGGING
# ──────────────────────────────────────────────────────────────────────────────
FILE_NAME: str = "app/routes/reviews.py"
logger = logging.getLogger(FILE_NAME)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/reviews", tags=["reviews"])

# ─── Google Places Client Initialization ─────────────────────────────────────
api_key = os.getenv("GOOGLE_PLACES_API_KEY")
if not api_key:
    logger.critical("MISSING_API_KEY: GOOGLE_PLACES_API_KEY is not defined.")
    raise RuntimeError("Google Places API key not set in environment")

gmaps = googlemaps.Client(key=api_key)

# ─── Default Reference Date ──────────────────────────────────────────────────
DEFAULT_DATE_FROM = datetime(2026, 2, 21, tzinfo=timezone.utc)

def _parse_date_env(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    fmts = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"]
    for fmt in fmts:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except Exception:
        logger.warning(f"DATE_PARSE_FAILURE: Unable to parse date string: {value}")
        return None

def _get_date_window() -> Tuple[datetime, datetime]:
    env_from = _parse_date_env(os.getenv("REVIEWS_DATE_FROM"))
    env_to = _parse_date_env(os.getenv("REVIEWS_DATE_TO"))
    start_date = env_from or DEFAULT_DATE_FROM
    end_date = env_to or datetime.now(timezone.utc)
    if end_date < start_date:
        start_date, end_date = end_date, start_date
    start_date = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
    end_date = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)
    return start_date, end_date

# ─── Fetch & Save Reviews Logic ───────────────────────────────────────────────
def fetch_and_save_reviews(company: Company, db: Session, max_reviews: int = 50) -> int:
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
            review_date = datetime.fromtimestamp(review_time, tz=timezone.utc) if review_time else None
            existing = db.query(Review).filter(
                Review.company_id == company.id,
                Review.text == rev.get("text", ""),
                Review.rating == rev.get("rating"),
                Review.review_date == review_date
            ).first()
            if existing: continue
            new_review = Review(
                company_id=company.id,
                text=rev.get("text", ""),
                rating=rev.get("rating"),
                reviewer_name=rev.get("author_name", "Anonymous"),
                review_date=review_date,
                fetch_at=datetime.now(timezone.utc)
            )
            db.add(new_review)
            added_count += 1
        new_rating, new_total = result.get("rating"), result.get("user_ratings_total")
        if added_count > 0 or new_rating is not None or new_total is not None:
            if new_rating is not None: company.google_rating = new_rating
            if new_total is not None: company.user_ratings_total = new_total
            db.commit()
        return added_count
    except Exception as e:
        logger.error(f"FETCH_ERROR: {e}")
        return 0

# ─── Analytics Helpers ───────────────────────────────────────────────────────
def classify_sentiment(rating: float | None) -> str:
    if rating is None: return "Neutral"
    return "Positive" if rating >= 4 else "Neutral" if rating == 3 else "Negative"

def extract_keywords(text: str | None) -> List[str]:
    if not text: return []
    text = re.sub(r"[^\w\s]", "", text.lower())
    words = text.split()
    stopwords = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "the", "this", "is", "it", "to", "with", "was", "of", "in", "on"}
    return [w for w in words if w not in stopwords and len(w) > 2]

ACTION_MAP: Dict[str, str] = {
    "wait": "Optimize peak-hour staffing levels to reduce response latency.",
    "service": "Implement mandatory customer service training for front-end staff.",
    "price": "Review pricing strategy against local competitors for value alignment.",
    "clean": "Increase janitorial frequency and implement visible hygiene logs.",
    "quality": "Audit product supply chain to address recurring defect mentions."
}

def _action_for_keyword(keyword: str) -> str:
    for k, action in ACTION_MAP.items():
        if k in keyword: return action
    return "Conduct root-cause analysis and monitor sentiment drift weekly."

# ─── Dashboard Core (The Decision Engine) ───────────────────────────────────
def get_review_summary_data(reviews: List[Review], company: Company, months: int = 6) -> Dict[str, Any]:
    start_date, end_date = _get_date_window()
    
    # FILTER FIX: Datetime to Datetime comparison
    windowed_reviews = [
        r for r in reviews 
        if r.review_date and start_date <= r.review_date.replace(tzinfo=timezone.utc) <= end_date
    ]

    if not windowed_reviews:
        return {"company_name": company.name or "N/A", "total_reviews": 0, "avg_rating": 0.0, "sentiments": {"Positive": 0, "Neutral": 0, "Negative": 0}, "reviews": [], "ai_recommendations": [], "risk_score": 0}

    total_reviews = len(windowed_reviews)
    valid_ratings = [r.rating for r in windowed_reviews if r.rating is not None]
    avg_rating = round(sum(valid_ratings)/total_reviews, 2) if total_reviews else 0.0
    
    sentiments_count = {"Positive": 0, "Neutral": 0, "Negative": 0}
    pos_kw, neg_kw = [], []
    monthly_ratings = defaultdict(list)
    review_list = []

    for r in windowed_reviews:
        sentiment = classify_sentiment(r.rating)
        sentiments_count[sentiment] += 1
        keywords = extract_keywords(r.text)
        
        if sentiment == "Positive": pos_kw.extend(keywords)
        elif sentiment == "Negative": neg_kw.extend(keywords)
        
        mkey = r.review_date.strftime("%Y-%m")
        monthly_ratings[mkey].append(r.rating or 0.0)

        review_list.append({
            "id": r.id, "review_text": r.text or "", "rating": r.rating,
            "reviewer_name": r.reviewer_name or "Anonymous",
            "review_date": r.review_date.isoformat(), "sentiment": sentiment,
            "suggested_reply": "Thank you for your feedback. We value your input."
        })

    # Graphs: Trend Data
    trend_data = [{"month": m, "avg_rating": round(sum(v)/len(v), 2), "count": len(v)} for m, v in sorted(monthly_ratings.items())]

    # AI Recommendation Logic
    top_neg = Counter(neg_kw).most_common(5)
    ai_recs = [{
        "weak_area": k, "issue_mentions": v, "priority": "High" if v > 2 else "Medium",
        "recommended_action": _action_for_keyword(k),
        "expected_outcome": "Reduced churn and improved brand reputation."
    } for k, v in top_neg]

    # Risk Score Calculation (0-100)
    neg_ratio = sentiments_count["Negative"] / total_reviews
    risk_score = round(neg_ratio * 100, 2)

    return {
        "company_name": company.name,
        "google_rating": getattr(company, "google_rating", 0),
        "google_total_ratings": getattr(company, "user_ratings_total", 0),
        "data_completion_percent": round((total_reviews / getattr(company, "user_ratings_total", 1)) * 100, 2),
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "sentiments": sentiments_count,
        "positive_keywords": [k for k, _ in Counter(pos_kw).most_common(8)],
        "negative_keywords": [k for k, _ in top_neg],
        "trend_data": trend_data,
        "weak_areas": [{"keyword": k, "mentions": v} for k, v in top_neg],
        "strength_areas": [{"keyword": k, "mentions": v} for k, v in Counter(pos_kw).most_common(8)],
        "ai_recommendations": ai_recs,
        "risk_score": risk_score,
        "reviews": sorted(review_list, key=lambda x: x["review_date"], reverse=True)[:15]
    }

# ─── Endpoints ──────────────────────────────────────────────────────────────
@router.get("/summary/{company_id}")
def reviews_summary(company_id: int, refresh: bool = False, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company: raise HTTPException(404, "Company not found")
    if refresh: fetch_and_save_reviews(company, db)
    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    return get_review_summary_data(reviews, company)

@router.get("/my-companies")
def get_my_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).all()
    return [{"id": c.id, "name": c.name, "city": getattr(c, "city", "N/A")} for c in companies]
