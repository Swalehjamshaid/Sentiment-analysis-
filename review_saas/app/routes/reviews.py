# FILE: review_saas/app/routes/reviews.py

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

import os
import re
import logging

# Optional Google client (Places only)
try:
    import googlemaps
except Exception:
    googlemaps = None


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
# Config
# ─────────────────────────────────────────────────────────────

def _resolve_places_api_key() -> Tuple[Optional[str], str]:
    key = os.getenv("GOOGLE_PLACES_API_KEY")
    if key:
        return key, "GOOGLE_PLACES_API_KEY"
    alt = os.getenv("GOOGLE_MAPS_API_KEY")
    if alt:
        logger.warning("Falling back to GOOGLE_MAPS_API_KEY for Places.")
        return alt, "GOOGLE_MAPS_API_KEY"
    return None, "NONE"


api_key, api_key_source = _resolve_places_api_key()

gmaps = None
if api_key and googlemaps:
    try:
        gmaps = googlemaps.Client(key=api_key)
        logger.info(f"Google Places client initialized using {api_key_source}")
    except Exception as e:
        logger.warning(f"Failed to initialize Google Maps client: {e}")

USE_GBP_API = os.getenv("USE_GBP_API", "false").lower() == "true"
GBP_LOCATION_NAME = os.getenv("GBP_LOCATION_NAME")
GBP_ACCESS_TOKEN = os.getenv("GBP_ACCESS_TOKEN")

FIXED_DEFAULT_START = datetime(2026, 2, 21, tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────
# NLP Helpers
# ─────────────────────────────────────────────────────────────

_STOPWORDS = {
    "a","an","and","are","as","at","be","by","for","from",
    "the","this","is","it","to","with","was","of","in","on",
    "or","we","you","our","your","but","not","they","them",
    "very","really","just","too"
}

ASPECT_LEXICON = {
    "Service": ["service","staff","attitude","rude","friendly","helpful","manager"],
    "Speed": ["wait","slow","delay","queue","time","late"],
    "Price": ["price","expensive","cheap","overpriced","value"],
    "Cleanliness": ["clean","dirty","smell","hygiene"],
    "Quality": ["quality","defect","broken","taste","fresh","stale","cold"],
    "Availability": ["stock","availability","sold","item"],
    "Environment": ["noise","crowd","parking","space","ambience"],
    "Digital": ["payment","card","terminal","app","crash","online","wifi"],
}

ACTION_MAP = {
    "wait": "Optimize peak-hour staffing and queue flow.",
    "service": "Launch service excellence workshop.",
    "price": "Review pricing vs competitors.",
    "clean": "Increase cleaning frequency + checklists.",
    "quality": "Audit suppliers and implement QA loop.",
    "stock": "Improve forecasting and restock alerts.",
    "noise": "Add acoustic dampening or zoning.",
    "payment": "Improve terminal reliability monitoring.",
    "rude": "Reinforce code-of-conduct coaching.",
}

def classify_sentiment(rating: Optional[float]) -> str:
    if rating is None or rating == 3:
        return "Neutral"
    return "Positive" if rating >= 4 else "Negative"

def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", text.lower())

def extract_keywords(text: Optional[str]) -> List[str]:
    if not text:
        return []
    words = _normalize(text).split()
    return [w for w in words if w not in _STOPWORDS and len(w) > 2]

def map_aspects(tokens: List[str]) -> List[str]:
    found = set()
    for aspect, words in ASPECT_LEXICON.items():
        if any(w in tokens for w in words):
            found.add(aspect)
    return list(found)

def _action_for_keyword(keyword: str) -> str:
    for k, v in ACTION_MAP.items():
        if k in keyword.lower():
            return v
    return "Run root-cause analysis and 5-Whys workshop."

def _parse_review_date(r: Review) -> Optional[datetime]:
    if not r.review_date:
        return None
    if isinstance(r.review_date, datetime):
        return r.review_date.astimezone(timezone.utc) if r.review_date.tzinfo else r.review_date.replace(tzinfo=timezone.utc)
    return None


# ─────────────────────────────────────────────────────────────
# Sync Optimized (NO N+1 QUERIES)
# ─────────────────────────────────────────────────────────────

def _preload_existing_keys(db: Session, company_id: int):
    existing = db.query(Review).filter(Review.company_id == company_id).all()
    return {(r.text, r.rating, r.review_date) for r in existing}

def fetch_and_save_reviews_places(company: Company, db: Session, max_reviews: int = 50) -> int:
    if not gmaps or not company.place_id:
        return 0

    existing_keys = _preload_existing_keys(db, company.id)

    result = gmaps.place(place_id=company.place_id,
                         fields=["reviews","rating","user_ratings_total"]).get("result", {})

    reviews_data = (result.get("reviews", []) or [])[:max_reviews]
    added = 0

    for rev in reviews_data:
        review_date = datetime.fromtimestamp(rev["time"], tz=timezone.utc) if rev.get("time") else None
        key = (rev.get("text",""), rev.get("rating"), review_date)

        if key in existing_keys:
            continue

        db.add(Review(
            company_id=company.id,
            text=key[0],
            rating=key[1],
            reviewer_name=rev.get("author_name","Anonymous"),
            review_date=review_date,
            fetch_at=datetime.now(timezone.utc)
        ))
        added += 1

    if added:
        db.commit()

    company.google_rating = result.get("rating")
    company.user_ratings_total = result.get("user_ratings_total")
    db.commit()

    return added


# ─────────────────────────────────────────────────────────────
# Analysis Engine
# ─────────────────────────────────────────────────────────────

def _detect_trend(trend_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(trend_data) < 3:
        return {"signal":"insufficient_data","delta":0.0}

    data = sorted(trend_data, key=lambda x: x["month"])

    if len(data) == 3:
        delta = round(data[-1]["avg_rating"] - data[0]["avg_rating"], 2)
    else:
        last3 = data[-3:]
        prev3 = data[-6:-3]
        last_avg = sum(x["avg_rating"] for x in last3)/3
        prev_avg = sum(x["avg_rating"] for x in prev3)/3 if prev3 else last_avg
        delta = round(last_avg-prev_avg,2)

    if delta <= -0.3:
        return {"signal":"declining","delta":delta}
    if delta >= 0.3:
        return {"signal":"improving","delta":delta}
    return {"signal":"stable","delta":delta}


def get_review_summary_data(
    reviews: List[Review],
    company: Company,
    start_override: Optional[datetime] = None,
    end_override: Optional[datetime] = None
):

    start = start_override or FIXED_DEFAULT_START
    end = end_override or datetime.now(timezone.utc)
    if end < start:
        start, end = end, start

    windowed = []
    for r in reviews:
        r_dt = _parse_review_date(r)
        if r_dt and start <= r_dt <= end:
            windowed.append(r)

    if not windowed:
        return {
            "company_name": company.name,
            "total_reviews": 0,
            "avg_rating": 0.0,
            "risk_score": 0,
            "risk_level": "Low",
            "trend_data": [],
            "ai_recommendations": [],
            "reviews": []
        }

    sentiments = {"Positive":0,"Neutral":0,"Negative":0}
    trend_data = defaultdict(list)
    neg_tokens = []
    aspect_counts = defaultdict(lambda: {"pos":0,"neg":0})

    for r in windowed:
        sentiment = classify_sentiment(r.rating)
        sentiments[sentiment]+=1

        tokens = extract_keywords(r.text)
        aspects = map_aspects(tokens)

        if sentiment=="Negative":
            neg_tokens.extend(tokens)

        for asp in aspects:
            if sentiment=="Positive":
                aspect_counts[asp]["pos"]+=1
            if sentiment=="Negative":
                aspect_counts[asp]["neg"]+=1

        r_dt = _parse_review_date(r)
        if r_dt:
            trend_data[r_dt.strftime("%Y-%m")].append(r.rating or 0)

    trend_list = [{"month":m,"avg_rating":round(sum(v)/len(v),2)}
                  for m,v in sorted(trend_data.items())]

    trend_signal = _detect_trend(trend_list)

    total = len(windowed)
    avg = round(sum(r.rating for r in windowed if r.rating)/total,2)

    neg_share = sentiments["Negative"]/total
    risk_score = round(neg_share*100 + (10 if trend_signal["signal"]=="declining" else 0),2)

    risk_level = "High" if risk_score>=40 else "Medium" if risk_score>=20 else "Low"

    neg_counter = Counter(neg_tokens)

    recommendations = []
    seen = set()

    for keyword, count in neg_counter.most_common(5):
        if keyword in seen:
            continue
        seen.add(keyword)
        recommendations.append({
            "area":keyword,
            "priority":"High" if count>=5 else "Medium",
            "action":_action_for_keyword(keyword)
        })

    return {
        "company_name": company.name,
        "total_reviews": total,
        "avg_rating": avg,
        "sentiments": sentiments,
        "trend_data": trend_list,
        "trend": trend_signal,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "ai_recommendations": recommendations,
        "payload_version":"3.0"
    }


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("/summary/{company_id}")
def reviews_summary(company_id:int, db:Session=Depends(get_db)):
    company = db.query(Company).filter(Company.id==company_id).first()
    if not company:
        raise HTTPException(status_code=404,detail="Company not found")

    reviews = db.query(Review).filter(Review.company_id==company_id).all()
    return get_review_summary_data(reviews,company)


@router.get("/sync/{company_id}")
def reviews_sync(company_id:int, db:Session=Depends(get_db)):
    company = db.query(Company).filter(Company.id==company_id).first()
    if not company:
        raise HTTPException(status_code=404,detail="Company not found")

    if not gmaps:
        return {"ok":False,"reason":"Google client not initialized"}

    added = fetch_and_save_reviews_places(company,db)
    return {"ok":True,"added":added}


@router.get("/diagnostics")
def reviews_diagnostics():
    return {
        "googlemaps_available": googlemaps is not None,
        "places_client_initialized": gmaps is not None,
        "use_gbp_api": USE_GBP_API,
        "gbp_location_set": bool(GBP_LOCATION_NAME),
        "gbp_token_present": bool(GBP_ACCESS_TOKEN)
    }
