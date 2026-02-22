# FILE: review_saas/app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

import os
import re
import logging
import math

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

API_TOKEN = os.getenv("API_TOKEN")  # For POST /reviews/company

# Keep the fixed start to preserve existing behavior
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

ASPECT_LEXICON: Dict[str, List[str]] = {
    "Service": ["service","staff","attitude","rude","friendly","helpful","manager"],
    "Speed": ["wait","slow","delay","queue","time","late"],
    "Price": ["price","expensive","cheap","overpriced","value"],
    "Cleanliness": ["clean","dirty","smell","hygiene"],
    "Quality": ["quality","defect","broken","taste","fresh","stale","cold"],
    "Availability": ["stock","availability","sold","item"],
    "Environment": ["noise","crowd","parking","space","ambience"],
    "Digital": ["payment","card","terminal","app","crash","online","wifi"],
}

EMOTION_LEXICON = {
    "anger": ["angry","furious","outraged","rage","mad","livid","disgusting","hate","terrible"],
    "joy": ["happy","delighted","amazing","love","great","wonderful","fantastic","pleased","satisfied"],
    "frustration": ["frustrated","annoyed","irritated","disappointed","upset","letdown","ugh","tired"],
    # Simple multilingual hints (lightweight)
    "anger_multi": ["enojado","arrabbiato","wütend","عصبي","生气","गुस्सा"],
    "joy_multi": ["feliz","felice","glücklich","سعيد","高兴","खुश"],
    "frustration_multi": ["frustrado","frustrato","frustriert","محبط","沮丧","हताश"],
}

ACTION_MAP: Dict[str, str] = {
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

def _score_from_sentiment(label: str) -> float:
    # Map to numeric [-1, 1]
    if label == "Positive": return 1.0
    if label == "Negative": return -1.0
    return 0.0

def _emotion_from_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = _normalize(text)
    if any(w in t for w in EMOTION_LEXICON["anger"] + EMOTION_LEXICON["anger_multi"]):
        return "anger"
    if any(w in t for w in EMOTION_LEXICON["frustration"] + EMOTION_LEXICON["frustration_multi"]):
        return "frustration"
    if any(w in t for w in EMOTION_LEXICON["joy"] + EMOTION_LEXICON["joy_multi"]):
        return "joy"
    return None

def _confidence_heuristic(rating: Optional[float], text: Optional[str]) -> float:
    # Simple heuristic: strong when rating far from neutral or text has emotion keywords
    conf = 0.5
    if rating is not None:
        conf = 0.6 + 0.4 * (abs((rating or 3) - 3) / 2)  # 3..5 -> up to +0.4; 1..3 similar
    emo = _emotion_from_text(text)
    if emo:
        conf = min(0.95, conf + 0.2)
    return round(conf, 2)

# ─────────────────────────────────────────────────────────────
# Sync Optimized (NO N+1 QUERIES)
# ─────────────────────────────────────────────────────────────
def _preload_existing_keys(db: Session, company_id: int):
    existing = db.query(Review).filter(Review.company_id == company_id).all()
    return {(r.text, r.rating, r.review_date) for r in existing}

def fetch_and_save_reviews_places(company: Company, db: Session, max_reviews: int = 50) -> int:
    if not gmaps or not getattr(company, "place_id", None):
        return 0

    existing_keys = _preload_existing_keys(db, company.id)

    result = gmaps.place(
        place_id=company.place_id,
        fields=["reviews","rating","user_ratings_total"]
    ).get("result", {})

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

    # Update company aggregates if model supports these fields
    if hasattr(company, "google_rating"):
        company.google_rating = result.get("rating")
    if hasattr(company, "user_ratings_total"):
        company.user_ratings_total = result.get("user_ratings_total")
    db.commit()

    return added

# ─────────────────────────────────────────────────────────────
# Analysis & Aggregations
# ─────────────────────────────────────────────────────────────
def _detect_trend(trend_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(trend_data) < 3:
        return {"signal": "insufficient_data", "delta": 0.0}

    data = sorted(trend_data, key=lambda x: x["month"])

    if len(data) == 3:
        delta = round(data[-1]["avg_rating"] - data[0]["avg_rating"], 2)
    else:
        last3 = data[-3:]
        prev3 = data[-6:-3]
        last_avg = sum(x["avg_rating"] for x in last3) / 3
        prev_avg = sum(x["avg_rating"] for x in prev3) / 3 if prev3 else last_avg
        delta = round(last_avg - prev_avg, 2)

    if delta <= -0.3:
        return {"signal": "declining", "delta": delta}
    if delta >= 0.3:
        return {"signal": "improving", "delta": delta}
    return {"signal": "stable", "delta": delta}

def _daily_buckets(reviews: List[Review], days: int) -> List[Dict[str, Any]]:
    """Return last N days buckets with avg rating & sentiment score."""
    end = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=0)
    start = end - timedelta(days=days-1)
    buckets: Dict[str, Dict[str, Any]] = {}
    for i in range(days):
        d = (start + timedelta(days=i)).date().isoformat()
        buckets[d] = {"date": d, "ratings": [], "scores": []}

    for r in reviews:
        dt = _parse_review_date(r)
        if not dt:
            continue
        if dt < start or dt > end:
            continue
        d = dt.date().isoformat()
        label = classify_sentiment(r.rating)
        score = _score_from_sentiment(label)
        buckets[d]["ratings"].append(r.rating or 0)
        buckets[d]["scores"].append(score)

    series = []
    for d in sorted(buckets.keys()):
        rs = buckets[d]["ratings"]
        ss = buckets[d]["scores"]
        series.append({
            "date": d,
            "avg_rating": round(sum(rs)/len(rs), 2) if rs else None,
            "sent_score": round(sum(ss)/len(ss), 3) if ss else 0.0
        })
    return series

def _window_summary(reviews: List[Review], days: int) -> Dict[str, Any]:
    series = _daily_buckets(reviews, days)
    values = [x["sent_score"] for x in series]
    avg = round(sum(values)/len(values), 3) if values else 0.0
    # Spike detection: last 3-day vs previous 3-day mean
    if len(values) >= 6:
        last3 = values[-3:]
        prev3 = values[-6:-3]
        delta = round((sum(last3)/3) - (sum(prev3)/3), 3)
    else:
        delta = 0.0
    return {"avg_score": avg, "delta": delta, "series": series}

def get_review_summary_data(
    reviews: List[Review],
    company: Company,
    start_override: Optional[datetime] = None,
    end_override: Optional[datetime] = None
):
    # Preserve window behavior
    start = start_override or FIXED_DEFAULT_START
    end = end_override or datetime.now(timezone.utc)
    if end < start:
        start, end = end, start

    windowed: List[Review] = []
    for r in reviews:
        r_dt = _parse_review_date(r)
        if r_dt and start <= r_dt <= end:
            windowed.append(r)

    # Ensure consistent structure even when no data (additive keys only)
    if not windowed:
        return {
            "company_name": getattr(company, "name", f"Company {getattr(company, 'id', '')}"),
            "total_reviews": 0,
            "avg_rating": 0.0,
            "risk_score": 0,
            "risk_level": "Low",
            "trend_data": [],
            "trend": {"signal": "insufficient_data", "delta": 0.0},
            "sentiments": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "ai_recommendations": [],
            "reviews": [],
            "payload_version": "3.0"
        }

    sentiments = {"Positive":0, "Neutral":0, "Negative":0}
    trend_data: Dict[str, List[float]] = defaultdict(list)
    neg_tokens: List[str] = []
    aspect_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"pos":0,"neg":0})

    for r in windowed:
        sentiment = classify_sentiment(r.rating)
        sentiments[sentiment] += 1

        tokens = extract_keywords(r.text)
        aspects = map_aspects(tokens)

        if sentiment == "Negative":
            neg_tokens.extend(tokens)

        for asp in aspects:
            if sentiment == "Positive":
                aspect_counts[asp]["pos"] += 1
            if sentiment == "Negative":
                aspect_counts[asp]["neg"] += 1

        r_dt = _parse_review_date(r)
        if r_dt:
            trend_data[r_dt.strftime("%Y-%m")].append(r.rating or 0)

    trend_list = [
        {"month": m, "avg_rating": round(sum(v)/len(v), 2)}
        for m, v in sorted(trend_data.items())
    ]

    trend_signal = _detect_trend(trend_list)

    total = len(windowed)
    rated_values = [r.rating for r in windowed if r.rating is not None]
    avg = round(sum(rated_values) / len(rated_values), 2) if rated_values else 0.0

    neg_share = sentiments["Negative"] / total if total else 0
    risk_score = round(neg_share * 100 + (10 if trend_signal["signal"] == "declining" else 0), 2)
    risk_level = "High" if risk_score >= 40 else "Medium" if risk_score >= 20 else "Low"

    neg_counter = Counter(neg_tokens)

    recommendations = []
    seen = set()
    for keyword, count in neg_counter.most_common(5):
        if keyword in seen:
            continue
        seen.add(keyword)
        recommendations.append({
            "area": keyword,
            "priority": "High" if count >= 5 else "Medium",
            "action": _action_for_keyword(keyword)
        })

    return {
        "company_name": getattr(company, "name", f"Company {getattr(company, 'id', '')}"),
        "total_reviews": total,
        "avg_rating": avg,
        "sentiments": sentiments,
        "trend_data": trend_list,
        "trend": trend_signal,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "ai_recommendations": recommendations,
        "payload_version": "3.0"
    }

# ─────────────────────────────────────────────────────────────
# New: Companies Overview & Add Company API
# ─────────────────────────────────────────────────────────────
def _health_from_risk(risk_level: str) -> str:
    if risk_level == "High": return "Red"
    if risk_level == "Medium": return "Yellow"
    return "Green"

def _pct(n: int, d: int) -> float:
    return round((n / d) * 100, 2) if d else 0.0

def _compute_overview_for_company(db: Session, c: Company) -> Dict[str, Any]:
    reviews = db.query(Review).filter(Review.company_id == c.id).all()

    # Full-window summary (existing logic)
    base = get_review_summary_data(reviews, c)

    # Windowed analytics
    last7 = _window_summary(reviews, 7)
    last30 = _window_summary(reviews, 30)
    last90 = _window_summary(reviews, 90)

    # Negative surge alert: last7 avg < prev7 avg by threshold (e.g., -0.25)
    neg_surge = False
    if len(last30["series"]) >= 14:
        last7_vals = [x["sent_score"] for x in last30["series"][-7:]]
        prev7_vals = [x["sent_score"] for x in last30["series"][-14:-7]]
        if last7_vals and prev7_vals:
            diff = (sum(last7_vals)/7) - (sum(prev7_vals)/7)
            neg_surge = diff <= -0.25

    sentiments = base.get("sentiments", {"Positive":0,"Neutral":0,"Negative":0})
    total = base["total_reviews"]
    pos_pct = _pct(sentiments.get("Positive",0), total)
    neu_pct = _pct(sentiments.get("Neutral",0), total)
    neg_pct = _pct(sentiments.get("Negative",0), total)

    perf90_label = "Improving" if last90["delta"] > 0.05 else "Declining" if last90["delta"] < -0.05 else "Stable"

    overview = {
        "id": c.id,
        "name": getattr(c, "name", f"Company {c.id}"),
        "avg_rating": base["avg_rating"],
        "total_reviews": base["total_reviews"],
        "pos_pct": pos_pct,
        "neu_pct": neu_pct,
        "neg_pct": neg_pct,
        "risk_level": base["risk_level"],
        "health": _health_from_risk(base["risk_level"]),
        "trend7": last7["series"],     # [{date, avg_rating, sent_score}]
        "trend30": last30["series"],
        "perf90": {
            "avg_score": last90["avg_score"],
            "delta": last90["delta"],
            "label": perf90_label
        },
        "alerts": {
            "negative_surge": neg_surge
        }
    }
    return overview

@router.get("/companies/overview")
def companies_overview(db: Session = Depends(get_db)):
    """
    Returns overview metrics per company for the central dashboard.
    Non-breaking: new endpoint.
    """
    companies = db.query(Company).all()
    results = []
    for c in companies:
        try:
            results.append(_compute_overview_for_company(db, c))
        except Exception as e:
            logger.error(f"Overview compute failed for company {getattr(c, 'id', '?')}: {e}")
            results.append({
                "id": getattr(c, "id", None),
                "name": getattr(c, "name", "Unknown"),
                "error": "overview_failed"
            })
    return {"items": results, "generated_at": datetime.now(timezone.utc).isoformat()}

def _validate_api_token(x_api_key: Optional[str], auth: Optional[str]):
    if not API_TOKEN:
        raise HTTPException(status_code=503, detail="API token not configured on server")
    token = None
    if x_api_key:
        token = x_api_key.strip()
    elif auth and auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API token")

@router.post("/company")
def add_company(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization")
):
    """
    Secure API to add new company.
    - Token validation via X-API-Key or Authorization: Bearer <token>.
    - Duplicate detection by name (case-insensitive) and place_id.
    - Attempts auto-fetch of reviews if Google Places configured and place_id provided.
    - Returns status (Processing/Active/Error) and the overview payload entry.
    """
    _validate_api_token(x_api_key, authorization)

    name = (payload.get("name") or "").strip()
    place_id = (payload.get("place_id") or "").strip() or None
    website = (payload.get("website") or "").strip() or None
    location = (payload.get("location") or "").strip() or None

    if not name or len(name) < 2:
        raise HTTPException(status_code=422, detail="Company name is required")

    # Duplicate detection
    existing = db.query(Company).filter(Company.name.ilike(name)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Company with same name already exists")

    if place_id:
        dup_place = db.query(Company).filter(Company.place_id == place_id).first()
        if dup_place:
            raise HTTPException(status_code=409, detail="Company with same place_id already exists")

    # Create company (supporting dynamic models)
    company = Company(name=name)
    if hasattr(company, "place_id"): company.place_id = place_id
    if hasattr(company, "website"): company.website = website
    if hasattr(company, "location"): company.location = location

    db.add(company)
    db.commit()
    db.refresh(company)

    status = "Processing"
    added = 0
    reason = None
    try:
        if place_id and gmaps:
            added = fetch_and_save_reviews_places(company, db)
            status = "Active"
        else:
            status = "Active"  # created, but no external ingestion
    except Exception as e:
        logger.error(f"Auto-ingestion failed for company {company.id}: {e}")
        status = "Error"
        reason = "ingestion_failed"

    # Build overview row so UI can appear instantly
    try:
        overview = _compute_overview_for_company(db, company)
    except Exception as e:
        logger.error(f"Overview build failed for company {company.id}: {e}")
        overview = {
            "id": company.id,
            "name": getattr(company, "name", "Unknown"),
            "error": "overview_failed"
        }

    return {
        "ok": True,
        "company_id": company.id,
        "status": status,
        "reason": reason,
        "auto_ingested_reviews": added,
        "overview": overview
    }

# ─────────────────────────────────────────────────────────────
# Existing Endpoints (unchanged IO)
# ─────────────────────────────────────────────────────────────
@router.get("/summary/{company_id}")
def reviews_summary(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    return get_review_summary_data(reviews, company)

@router.get("/sync/{company_id}")
def reviews_sync(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if not gmaps:
        return {"ok": False, "reason": "Google client not initialized"}

    added = fetch_and_save_reviews_places(company, db)
    return {"ok": True, "added": added}

@router.get("/diagnostics")
def reviews_diagnostics():
    return {
        "googlemaps_available": googlemaps is not None,
        "places_client_initialized": gmaps is not None,
        "use_gbp_api": USE_GBP_API,
        "gbp_location_set": bool(GBP_LOCATION_NAME),
        "gbp_token_present": bool(GBP_ACCESS_TOKEN)
    }
