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

# ─── Default Date ─────────────────────────────────────────────────────────────
DEFAULT_DATE_FROM = datetime(2026, 2, 21)

def _parse_date_env(value: str | None) -> datetime | None:
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
        return datetime.fromisoformat(value)
    except Exception:
        logger.warning(f"Unable to parse date: {value}")
        return None

def _get_date_window() -> tuple[datetime, datetime]:
    env_from = _parse_date_env(os.getenv("REVIEWS_DATE_FROM"))
    env_to = _parse_date_env(os.getenv("REVIEWS_DATE_TO"))
    start_date = env_from or DEFAULT_DATE_FROM
    end_date = env_to or datetime.utcnow()
    if end_date < start_date:
        start_date, end_date = end_date, start_date
    start_date = datetime(start_date.year, start_date.month, start_date.day)
    end_date = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
    return start_date, end_date

# ─── Fetch & Save Reviews ─────────────────────────────────────────────────────
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

# ─── Sentiment & Keywords ────────────────────────────────────────────────────
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

# ─── AI Action Mapping ───────────────────────────────────────────────────────
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
    return "Investigate root cause and implement corrective actions with weekly monitoring."

# ─── Dashboard & Decision Data ───────────────────────────────────────────────
def get_review_summary_data(reviews: List[Review], company: Company, months: int = 6) -> Dict[str, Any]:
    google_rating = getattr(company, "google_rating", None)
    google_total_ratings = getattr(company, "user_ratings_total", None)
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

    # Filter by date window
    windowed_reviews = [r for r in reviews if r.review_date and start_date <= r.review_date <= end_date]
    total_reviews = len(windowed_reviews)
    valid_ratings = [r.rating for r in windowed_reviews if r.rating is not None]
    avg_rating = round(sum(valid_ratings)/len(valid_ratings),2) if valid_ratings else 0.0
    data_completion_percent = round((total_reviews / google_total_ratings) * 100, 2) if google_total_ratings else 0
    sentiments_count = {"Positive":0,"Neutral":0,"Negative":0}
    positive_keywords = []
    negative_keywords = []
    monthly_ratings = defaultdict(list)
    monthly_counts = defaultdict(int)
    review_list = []

    def _month_key(dt: datetime) -> str:
        return dt.strftime("%Y-%m")

    # Build month keys
    months_all = []
    cursor = datetime(start_date.year, start_date.month, 1)
    end_anchor = datetime(end_date.year, end_date.month, 1)
    while cursor <= end_anchor:
        months_all.append(_month_key(cursor))
        year = cursor.year + (1 if cursor.month == 12 else 0)
        month = 1 if cursor.month == 12 else cursor.month + 1
        cursor = datetime(year, month, 1)
    months_window = months_all[-months:] if len(months_all) > months else months_all

    for r in windowed_reviews:
        sentiment = classify_sentiment(r.rating)
        sentiments_count[sentiment] += 1
        keywords = extract_keywords(r.text)
        if sentiment=="Positive":
            positive_keywords.extend(keywords)
        elif sentiment=="Negative":
            negative_keywords.extend(keywords)
        mkey = _month_key(r.review_date)
        if mkey in months_window:
            monthly_ratings[mkey].append(r.rating or 0.0)
            monthly_counts[mkey] += 1
        base_reply = generate_suggested_reply(sentiment)
        kw_hint = f" We noted your point about '{keywords[0]}'." if keywords else ""
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

    # Trend graph
    trend_data = []
    for m in months_window:
        ratings = monthly_ratings.get(m,[])
        avg = round(sum(ratings)/len(ratings),2) if ratings else 0
        cnt = monthly_counts.get(m,0)
        trend_data.append({"month": m, "avg_rating": avg, "count": cnt})

    # Keywords
    top_positive = Counter(positive_keywords).most_common(8)
    top_negative = Counter(negative_keywords).most_common(8)
    weak_areas = [{"keyword":k,"mentions":v} for k,v in top_negative]
    strength_areas = [{"keyword":k,"mentions":v} for k,v in top_positive]

    # Risk score
    negative_ratio = sentiments_count["Negative"]/max(1,total_reviews)
    last3 = trend_data[-3:] if len(trend_data)>=3 else trend_data
    slope_component = 0.0
    if len(last3)>=2:
        diffs = [last3[i]["avg_rating"]-last3[i-1]["avg_rating"] for i in range(1,len(last3))]
        decline = max(0.0, -sum(diffs)/len(diffs)/5.0)
        slope_component = min(1.0, decline)
    risk_score = round(100.0*(0.6*negative_ratio+0.4*slope_component),2)

    # AI Recommendations
    ai_recommendations = []
    for keyword,count in top_negative[:5]:
        ai_recommendations.append({
            "weak_area": keyword,
            "issue_mentions": count,
            "priority": "High" if count>3 or negative_ratio>0.2 else "Medium",
            "recommended_action": _action_for_keyword(keyword),
            "expected_outcome": "Improved customer satisfaction and reduction in negative sentiment."
        })
    if negative_ratio>0.2:
        ai_recommendations.append({
            "weak_area":"Overall customer satisfaction",
            "issue_mentions": int(total_reviews*negative_ratio),
            "priority":"High",
            "recommended_action":"Run a 4-week improvement sprint: staff coaching, SOP review, faster response SLAs, weekly sentiment monitoring.",
            "expected_outcome":"Reduce negative reviews and lift average rating over the next quarter."
        })

    reviews_sorted = sorted(
        review_list,
        key=lambda x: datetime.fromisoformat(x["review_date"]) if x["review_date"] else datetime.min,
        reverse=True
    )[:15]

    return {
        "company_name": company.name or "Unnamed Company",
        "google_rating": google_rating,
        "google_total_ratings": google_total_ratings,
        "data_completion_percent": data_completion_percent,
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "sentiments": sentiments_count,
        "positive_keywords": [k for k,_ in top_positive],
        "negative_keywords": [k for k,_ in top_negative],
        "trend_data": trend_data,
        "weak_areas": weak_areas,
        "strength_areas": strength_areas,
        "ai_recommendations": ai_recommendations,
        "risk_score": risk_score,
        "reviews": reviews_sorted
    }

# ─── Endpoints ───────────────────────────────────────────────────────────────
@router.post("/fetch/{company_id}")
def fetch_reviews(company_id:int, db:Session=Depends(get_db)):
    company = db.query(Company).filter(Company.id==company_id).first()
    if not company:
        raise HTTPException(404,"Company not found")
    added = fetch_and_save_reviews(company, db)
    return {"message":"Fresh fetch completed","new_reviews_added":added}

@router.get("/summary/{company_id}")
def reviews_summary(
    company_id:int,
    months:int=Query(6,description="Select months of data (1–any number)"),
    refresh:bool=Query(False,description="Fetch fresh reviews from Google"),
    from_date:str|None=Query(None,description="Start date DD/MM/YYYY or YYYY-MM-DD"),
    to_date:str|None=Query(None,description="End date DD/MM/YYYY or YYYY-MM-DD"),
    db:Session=Depends(get_db)
):
    company = db.query(Company).filter(Company.id==company_id).first()
    if not company:
        raise HTTPException(404,"Company not found")
    if refresh:
        fetch_and_save_reviews(company, db)
    # parse date range
    start_date = _parse_date_env(from_date) or DEFAULT_DATE_FROM
    end_date = _parse_date_env(to_date) or datetime.utcnow()
    if end_date < start_date:
        start_date, end_date = end_date, start_date
    reviews = db.query(Review).filter(
        Review.company_id==company_id,
        Review.review_date>=start_date,
        Review.review_date<=end_date
    ).all()
    return get_review_summary_data(reviews, company, months=months)

@router.get("/my-companies")
def get_my_companies(db:Session=Depends(get_db)):
    companies = db.query(Company).all()
    return [
        {"id":c.id,"name":c.name or "Unnamed","place_id":c.place_id,"city":getattr(c,"city","N/A")}
        for c in sorted(companies,key=lambda x:(x.name or "").lower())
    ]
