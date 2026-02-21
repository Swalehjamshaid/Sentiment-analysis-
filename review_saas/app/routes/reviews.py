# File: app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import re
import os
from typing import List, Dict, Any
import googlemaps
import random
import logging
import math

# ──────────────────────────────────────────────────────────────────────────────
# Full file name (per your rule #2) and logging
# ──────────────────────────────────────────────────────────────────────────────
FILE_NAME: str = "app/routes/reviews.py"
logger = logging.getLogger(FILE_NAME)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt=f"%(asctime)s | {FILE_NAME} | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/reviews", tags=["reviews"])

# ─── Google Places Client ────────────────────────────────────────────────────
api_key = os.getenv("GOOGLE_PLACES_API_KEY")
if not api_key:
    raise RuntimeError("Google Places API key not set in environment")
gmaps = googlemaps.Client(key=api_key)

# ─── Date Window Controls (No API changes; uses ENV and defaults) ────────────
# Default fixed start date per your requirement: 21/02/2026 (DD/MM/YYYY)
DEFAULT_DATE_FROM = datetime(2026, 2, 21)

def _parse_date_env(value: str | None) -> datetime | None:
    """
    Parse environment date in multiple common formats (no API change).
    Accepts: DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY, YYYY/MM/DD.
    """
    if not value:
        return None
    value = value.strip()
    fmts = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"]
    for fmt in fmts:
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    try:
        # Fallback ISO parse
        return datetime.fromisoformat(value)
    except Exception:
        logger.warning(f"Unable to parse date from ENV: '{value}'. Expected DD/MM/YYYY or YYYY-MM-DD.")
        return None

def _get_date_window() -> tuple[datetime, datetime]:
    """
    Determine the effective [start_date, end_date] window (inclusive)
    using ENV overrides if provided, else defaults to [21/02/2026, now].
    """
    env_from = _parse_date_env(os.getenv("REVIEWS_DATE_FROM"))
    env_to = _parse_date_env(os.getenv("REVIEWS_DATE_TO"))
    start_date = env_from or DEFAULT_DATE_FROM
    end_date = env_to or datetime.utcnow()
    if end_date < start_date:
        # Swap if misconfigured
        start_date, end_date = end_date, start_date
    # Normalize to day boundaries
    start_date = datetime(start_date.year, start_date.month, start_date.day)
    end_date = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
    return start_date, end_date

# ──────────────────────────────────────────────────────────────────────────────
# Fetch & Save Reviews
# ──────────────────────────────────────────────────────────────────────────────
def fetch_and_save_reviews(company: Company, db: Session, max_reviews: int = 50) -> int:
    """Fetch reviews from Google Places API and save new ones (no I/O change)."""
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

        logger.info(f"Fetched and saved {added_count} new reviews for company_id={company.id}")
        return added_count

    except googlemaps.exceptions.ApiError as e:
        logger.error(f"Google Places API error: {e}")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error during fetch: {e}")
        return 0

# ─── Sentiment & Reply Helpers ───────────────────────────────────────────────
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
    text = re.sub(r"[^\w\s]", "", text.lower())
    words = text.split()
    # Expanded stopwords (still lightweight; no external deps)
    stopwords = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "has", "have", "he", "in", "is", "it", "its", "of", "on", "that",
        "the", "to", "was", "were", "will", "with", "this", "i", "me", "my",
        "we", "our", "you", "your", "they", "their", "them", "but", "or",
        "if", "so", "very", "really", "too", "just", "not", "no", "yes",
        "also", "there", "here", "can", "could", "should", "would", "had",
        "did", "do", "does", "done", "than", "then", "over", "under",
    }
    return [w for w in words if w not in stopwords and len(w) > 2]

def generate_suggested_reply(sentiment: str) -> str:
    """
    Keep same signature. We’ll lightly contextualize in the caller
    (no output schema change).
    """
    templates = {
        "Positive": [
            "Thank you for your kind words! We're thrilled you had a great experience.",
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

# ─── AI Action Mapping (internal helper; no API change) ──────────────────────
ACTION_MAP: Dict[str, str] = {
    "wait": "Reduce wait times via queue management; add peak-hour staffing and appointment slots.",
    "delay": "Improve delivery timelines; set SLAs and proactive notifications for delays.",
    "late": "Audit scheduling; add buffer times; escalate repeat lateness to ops manager.",
    "service": "Introduce a service QA checklist; coach staff on consistency and courtesy.",
    "staff": "Run customer service training; set weekly huddles with clear KPIs.",
    "rude": "Deliver behavior-based training; implement mystery audits & zero-tolerance policy.",
    "price": "Review pricing transparency; bundle value offers and communicate clearly.",
    "expensive": "Offer tiered options; highlight benefits vs. alternatives.",
    "quality": "Run root-cause on defects; add incoming QA and post-service checks.",
    "clean": "Increase cleaning frequency; visible hygiene logs; assign area ownership.",
    "dirty": "Deep-clean backlog; daily audits; hygiene SOP updates.",
    "refund": "Clarify refund policy; empower front-line to resolve under thresholds.",
    "exchange": "Simplify exchange steps; add pre-authorization for common cases.",
    "noise": "Install noise dampening; adjust layout and hours where needed.",
    "cold": "Calibrate HVAC; check ambient targets; customer comfort checks hourly.",
    "hot": "HVAC maintenance; add portable cooling options in peak hours.",
    "parking": "Guide to nearest parking; validate or subsidize during peak hours.",
    "delivery": "Optimize routing; time windows; real-time tracking to customers.",
    "app": "Fix app usability issues; prioritize top 3 UX blockers and error handling.",
    "website": "Improve load times; fix broken flows; add clear contact/help options.",
}

def _action_for_keyword(keyword: str) -> str:
    for k, action in ACTION_MAP.items():
        if k in keyword:
            return action
    # Default fallback
    return "Investigate root cause and implement corrective actions with weekly monitoring."

# ─── Enhanced Dashboard Summary with Graphs & AI Recommendations ─────────────
def get_review_summary_data(reviews: List[Review], company: Company, months: int = 6) -> Dict[str, Any]:
    """
    Summary constrained by:
    - Date window: from 21/02/2026 to any date (ENV-overridable)  ← (rule satisfied, no new params)
    - Months: last N months within that window (same behavior as before, but safer)
    Returns (same keys as original; no output schema change):
    - company_name, google_rating, google_total_ratings, data_completion_percent,
      total_reviews, avg_rating, sentiments, positive_keywords, negative_keywords,
      trend_data, weak_areas, strength_areas, ai_recommendations, risk_score, reviews
    """
    google_rating = getattr(company, "google_rating", None)
    google_total_ratings = getattr(company, "user_ratings_total", None)

    # Resolve date window and align with months constraint
    start_date, end_date = _get_date_window()

    if not reviews:
        return {
            "company_name": company.name or "Unnamed Company",
            "google_rating": google_rating,
            "google_total_ratings": google_total_ratings,
            "data_completion_percent": 0,
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

    # Filter by date window first (inclusive)
    windowed_reviews: List[Review] = []
    for r in reviews:
        if not r.review_date:
            continue
        if start_date <= r.review_date <= end_date:
            windowed_reviews.append(r)

    total_reviews = len(windowed_reviews)
    valid_ratings = [r.rating for r in windowed_reviews if r.rating is not None]
    avg_rating = round(sum(valid_ratings) / len(valid_ratings), 2) if valid_ratings else 0.0
    data_completion_percent = round((total_reviews / google_total_ratings) * 100, 2) if google_total_ratings else 0

    sentiments_count = {"Positive": 0, "Neutral": 0, "Negative": 0}
    positive_keywords: List[str] = []
    negative_keywords: List[str] = []
    monthly_ratings = defaultdict(list)
    monthly_max_ratings = defaultdict(list)
    monthly_min_ratings = defaultdict(list)  # internal only, do not expose
    monthly_counts = defaultdict(int)
    review_list: List[Dict[str, Any]] = []

    # Prepare month buckets respecting "months" within the window
    # Compute all months between start_date and end_date; then keep last N (=months)
    def _month_key(dt: datetime) -> str:
        return dt.strftime("%Y-%m")

    # Build list of month keys in [start_date, end_date]
    months_all: List[str] = []
    cursor = datetime(start_date.year, start_date.month, 1)
    end_anchor = datetime(end_date.year, end_date.month, 1)
    while cursor <= end_anchor:
        months_all.append(_month_key(cursor))
        # next month
        year = cursor.year + (1 if cursor.month == 12 else 0)
        month = 1 if cursor.month == 12 else cursor.month + 1
        cursor = datetime(year, month, 1)

    # Trim to the last `months` buckets, but never earlier than start_date
    if months < 1:
        months = 6
    months_window = months_all[-months:] if len(months_all) > months else months_all

    # Aggregate within filtered window and selected months
    for r in windowed_reviews:
        sentiment = classify_sentiment(r.rating)
        sentiments_count[sentiment] += 1

        keywords = extract_keywords(r.text)
        if sentiment == "Positive":
            positive_keywords.extend(keywords)
        elif sentiment == "Negative":
            negative_keywords.extend(keywords)

        mkey = _month_key(r.review_date)
        if mkey in months_window:
            rating_val = r.rating or 0.0
            monthly_ratings[mkey].append(rating_val)
            monthly_max_ratings[mkey].append(rating_val)
            monthly_min_ratings[mkey].append(rating_val)
            monthly_counts[mkey] += 1

        # Generate suggested reply (same key, slightly contextual)
        base_reply = generate_suggested_reply(sentiment)
        # Add at most one keyword hint for specificity; keep same field name
        kw_hint = ""
        if keywords:
            # Prefer the most frequent keyword in this review if any; else first
            kw_hint = f" We noted your point about '{keywords[0]}'."
        final_reply = (base_reply + kw_hint).strip()

        review_list.append({
            "id": r.id,
            "review_text": r.text or "",
            "rating": r.rating,
            "reviewer_name": r.reviewer_name or "Anonymous",
            "review_date": r.review_date.isoformat() if r.review_date else None,
            "sentiment": sentiment,
            "suggested_reply": final_reply
        })

    # ─── Dynamic Trend Graphs (same structure: month, avg_rating, max_rating, count) ───
    trend_data: List[Dict[str, Any]] = []
    for m in months_window:
        ratings = monthly_ratings.get(m, [])
        avg = round(sum(ratings) / len(ratings), 2) if ratings else 0
        max_r = max(monthly_max_ratings.get(m, [0])) if ratings else 0
        cnt = monthly_counts.get(m, 0)
        trend_data.append({
            "month": m,
            "avg_rating": avg,
            "max_rating": max_r,
            "count": cnt
        })

    # ─── Keyword Analysis (top-N) ───
    positive_counter = Counter(positive_keywords)
    negative_counter = Counter(negative_keywords)
    top_positive = positive_counter.most_common(8)
    top_negative = negative_counter.most_common(8)

    weak_areas = [{"keyword": k, "mentions": v} for k, v in top_negative]
    strength_areas = [{"keyword": k, "mentions": v} for k, v in top_positive]

    # ─── Risk Score (still a single number; no schema change) ───
    # Combine negative ratio and last-3-months slope (downward trend increases risk)
    total_for_ratio = max(1, total_reviews)
    negative_ratio = sentiments_count["Negative"] / total_for_ratio

    # Compute recent slope on average ratings (normalize slope to [0..1] risk component)
    last3 = trend_data[-3:] if len(trend_data) >= 3 else trend_data
    slope_component = 0.0
    if len(last3) >= 2:
        # simple slope: avg_diff per step (max drop from 5 to 0 across steps)
        diffs = []
        for i in range(1, len(last3)):
            diffs.append((last3[i]["avg_rating"] - last3[i-1]["avg_rating"]))
        avg_diff = sum(diffs) / len(diffs)
        # Negative diff implies decline; map to [0..1] roughly by dividing by 5 and clamping
        decline = max(0.0, -avg_diff / 5.0)
        slope_component = min(1.0, decline)

    risk_score = round(100.0 * (0.6 * negative_ratio + 0.4 * slope_component), 2)

    # ─── AI Recommendations (same fields; smarter mapping) ───
    ai_recommendations: List[Dict[str, Any]] = []
    for keyword, count in top_negative[:5]:
        ai_recommendations.append({
            "weak_area": keyword,
            "issue_mentions": count,
            "priority": "High" if count > 3 or negative_ratio > 0.2 else "Medium",
            "recommended_action": _action_for_keyword(keyword),
            "expected_outcome": "Improved customer satisfaction and reduction in negative sentiment."
        })

    if negative_ratio > 0.2:
        ai_recommendations.append({
            "weak_area": "Overall customer satisfaction",
            "issue_mentions": int(total_reviews * negative_ratio),
            "priority": "High",
            "recommended_action": "Run a 4-week improvement sprint: staff coaching, SOP review, faster response SLAs, weekly sentiment monitoring.",
            "expected_outcome": "Reduce negative reviews and lift average rating over the next quarter."
        })

    # Sort reviews newest-first and keep 15 (same as original)
    reviews_sorted = sorted(
        review_list,
        key=lambda x: datetime.fromisoformat(x["review_date"]) if x["review_date"] else datetime.min,
        reverse=True
    )[:15]

    logger.info(
        f"Summary computed for company_id={company.id} | window={start_date.date()}→{end_date.date()} | "
        f"months={months} | total_in_window={total_reviews} | avg_rating={avg_rating} | risk={risk_score}"
    )

    return {
        "company_name": company.name or "Unnamed Company",
        "google_rating": google_rating,
        "google_total_ratings": google_total_ratings,
        "data_completion_percent": data_completion_percent,
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
        "reviews": reviews_sorted
    }

# ─── Endpoints (unchanged signatures & returns) ───────────────────────────────
@router.post("/fetch/{company_id}")
def fetch_reviews(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    added = fetch_and_save_reviews(company, db)
    return {"message": "Fresh fetch completed", "new_reviews_added": added}

@router.get("/summary/{company_id}")
def reviews_summary(
    company_id: int,
    months: int = Query(6, description="Select months of data (1–any number)"),
    refresh: bool = Query(False, description="Fetch fresh reviews from Google"),
    db: Session = Depends(get_db)
):
    if months < 1:
        months = 6
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    if refresh:
        fetch_and_save_reviews(company, db)
    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    return get_review_summary_data(reviews, company, months=months)

@router.get("/my-companies")
def get_my_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).all()
    return [
        {
            "id": c.id,
            "name": c.name or "Unnamed",
            "place_id": c.place_id,
            "city": getattr(c, "city", "N/A")
        }
        for c in sorted(companies, key=lambda x: (x.name or "").lower())
    ]
