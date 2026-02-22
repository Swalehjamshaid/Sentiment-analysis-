# FILE: review_saas/app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Depends, Header, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
import os
import re
import logging

# Optional Google client
try:
    import googlemaps
except ImportError:
    googlemaps = None

from ..db import get_db
from ..models import Review, Company

# ─────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────
logger = logging.getLogger("reviews")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/reviews", tags=["reviews"])

# ─────────────────────────────────────────────────────────────
# Config / Google Client
# ─────────────────────────────────────────────────────────────
def _resolve_places_api_key() -> Tuple[Optional[str], str]:
    """
    Prefer GOOGLE_PLACES_API_KEY; fall back to GOOGLE_MAPS_API_KEY for Places API.
    """
    key = os.getenv("GOOGLE_PLACES_API_KEY")
    if key:
        return key, "GOOGLE_PLACES_API_KEY"
    alt = os.getenv("GOOGLE_MAPS_API_KEY")
    if alt:
        logger.warning("Falling back to GOOGLE_MAPS_API_KEY → Places API")
        return alt, "GOOGLE_MAPS_API_KEY"
    return None, "NONE"

api_key, api_src = _resolve_places_api_key()

gmaps: Optional["googlemaps.Client"] = None
if api_key and googlemaps:
    try:
        gmaps = googlemaps.Client(key=api_key)
        logger.info(f"Google Places client initialized using {api_src}")
    except Exception as e:
        logger.warning(f"Failed to initialize Google Maps client: {e}")

API_TOKEN = os.getenv("API_TOKEN")

# ─────────────────────────────────────────────────────────────
# NLP helpers
# ─────────────────────────────────────────────────────────────
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "the", "this", "is", "it", "to", "with", "was", "of", "in", "on",
    "or", "we", "you", "our", "your", "but", "not", "they", "them",
    "very", "really", "just", "too", "i", "me", "my", "myself"
}

ASPECT_LEXICON: Dict[str, List[str]] = {
    "Service": ["service", "staff", "attitude", "rude", "friendly", "helpful", "manager", "waiter", "waitress"],
    "Speed": ["wait", "slow", "delay", "queue", "time", "late", "long"],
    "Price": ["price", "expensive", "cheap", "overpriced", "value", "cost", "rip"],
    "Cleanliness": ["clean", "dirty", "smell", "hygiene", "filthy", "bathroom"],
    "Quality": ["quality", "defect", "broken", "taste", "fresh", "stale", "cold", "hot"],
    "Availability": ["stock", "availability", "sold", "item", "out", "none"],
    "Environment": ["noise", "crowd", "parking", "space", "ambience", "loud", "temperature"],
    "Digital": ["payment", "card", "terminal", "app", "crash", "online", "wifi", "website"],
}

ACTION_MAP: Dict[str, str] = {
    "wait": "Optimize peak-hour staffing and queue management",
    "service": "Launch service excellence training program",
    "rude": "Reinforce staff code-of-conduct & soft-skills coaching",
    "price": "Conduct pricing benchmark vs local competitors",
    "clean": "Implement daily cleaning checklists + audits",
    "quality": "Audit suppliers and establish QA feedback loop",
    "stock": "Improve demand forecasting + automated restock alerts",
    "noise": "Add acoustic improvements or quieter zones",
    "payment": "Monitor & upgrade payment terminal reliability",
}

def classify_sentiment(rating: Optional[float]) -> str:
    if rating is None or rating == 3:
        return "Neutral"
    return "Positive" if rating >= 4 else "Negative"

def _normalize(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[^\w\s]", " ", text.lower())

def extract_keywords(text: Optional[str]) -> List[str]:
    if not text:
        return []
    words = _normalize(text).split()
    return [w for w in words if w not in _STOPWORDS and len(w) >= 3]

def map_aspects(tokens: List[str]) -> List[str]:
    found = set()
    for aspect, words in ASPECT_LEXICON.items():
        if any(w in tokens for w in words):
            found.add(aspect)
    return list(found)

def _action_for_keyword(keyword: str) -> str:
    k_lower = keyword.lower()
    for k, v in ACTION_MAP.items():
        if k in k_lower:
            return v
    return "Perform root-cause analysis (5-Whys) and define corrective action"

# ─────────────────────────────────────────────────────────────
# Google Place Helpers
# ─────────────────────────────────────────────────────────────
def _city_country_from_components(components: List[Dict]) -> Tuple[Optional[str], Optional[str]]:
    city = country = None
    for comp in components:
        types = comp.get("types", [])
        if any(t in types for t in ["locality", "postal_town", "administrative_area_level_2"]):
            city = city or comp.get("long_name")
        if "country" in types:
            country = comp.get("long_name")
    return city, country

def _enrich_place_detail(place_id: str) -> Dict[str, Any]:
    """
    Calls Places Details API and returns a normalized attribute payload.
    """
    if not gmaps:
        return {}
    try:
        fields = [
            "name", "place_id", "formatted_address", "address_components",
            "website", "international_phone_number", "rating", "user_ratings_total",
            "geometry", "opening_hours"
        ]
        res = gmaps.place(place_id=place_id, fields=fields).get("result", {}) or {}
        city, country = _city_country_from_components(res.get("address_components", []))
        loc = (res.get("geometry") or {}).get("location") or {}
        return {
            "name": res.get("name"),
            "place_id": res.get("place_id"),
            "formatted_address": res.get("formatted_address"),
            "city": city,
            "country": country,
            "website": res.get("website"),
            "international_phone_number": res.get("international_phone_number"),
            "rating": res.get("rating"),
            "user_ratings_total": res.get("user_ratings_total"),
            "location": {"lat": loc.get("lat"), "lng": loc.get("lng")} if loc else None,
            "opening_hours": {"weekday_text": (res.get("opening_hours") or {}).get("weekday_text", [])},
        }
    except Exception as e:
        logger.error(f"Google place detail failed for {place_id}: {e}")
        return {}

# ─────────────────────────────────────────────────────────────
# Date handling
# ─────────────────────────────────────────────────────────────
def _parse_review_date(r: Review) -> Optional[datetime]:
    if not r.review_date:
        return None
    dt = r.review_date
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None

def _parse_date_param(val: Optional[str], as_end: bool = False) -> Optional[datetime]:
    if not val:
        return None
    s = val.strip()
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            dt = dt.replace(tzinfo=timezone.utc) if not dt.tzinfo else dt.astimezone(timezone.utc)
            if "T" not in fmt:
                if as_end:
                    dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
                else:
                    dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            return dt
        except ValueError:
            continue
    raise HTTPException(422, "Invalid date format. Use YYYY-MM-DD or similar.")

# ─────────────────────────────────────────────────────────────
# DB & Google helpers
# ─────────────────────────────────────────────────────────────
def _preload_existing_keys(db: Session, company_id: int, since_days: int = 90) -> set:
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    existing = db.query(Review).filter(
        Review.company_id == company_id,
        Review.fetch_at >= cutoff
    ).all()
    return {(r.text or "", r.rating, r.review_date) for r in existing}

def fetch_and_save_reviews_places(company: Company, db: Session, max_reviews: int = 60) -> int:
    """
    Fetches recent reviews from Google Places for a company's place_id and saves
    new ones only (dedup by text/rating/date). Also updates company aggregates.
    """
    if not gmaps or not getattr(company, "place_id", None):
        return 0

    existing_keys = _preload_existing_keys(db, company.id)

    try:
        result = gmaps.place(
            place_id=company.place_id,
            fields=["reviews", "rating", "user_ratings_total"]
        ).get("result", {})
    except Exception as e:
        logger.error(f"Google Place API error for {company.place_id}: {e}")
        return 0

    reviews_data = (result.get("reviews") or [])[:max_reviews]
    added = 0
    now = datetime.now(timezone.utc)

    for rev in reviews_data:
        text = rev.get("text", "")
        rating = rev.get("rating")
        time_unix = rev.get("time")
        review_date = datetime.fromtimestamp(time_unix, tz=timezone.utc) if time_unix else None

        key = (text, rating, review_date)
        if key in existing_keys:
            continue

        db.add(Review(
            company_id=company.id,
            text=text,
            rating=rating,
            reviewer_name=rev.get("author_name", "Anonymous"),
            review_date=review_date,
            fetch_at=now
        ))
        added += 1

    if added:
        db.commit()

    if hasattr(company, "google_rating"):
        company.google_rating = result.get("rating")
    if hasattr(company, "user_ratings_total"):
        company.user_ratings_total = result.get("user_ratings_total")
    db.commit()

    return added

# ─────────────────────────────────────────────────────────────
# Core analysis logic
# ─────────────────────────────────────────────────────────────
def _daily_buckets_range(reviews: List[Review], start: datetime, end: datetime) -> List[Dict]:
    start_day = start.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end_day = end.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
    days_diff = (end_day.date() - start_day.date()).days + 1
    if days_diff < 1:
        return []

    buckets: Dict[str, Dict] = {}
    for i in range(days_diff):
        d = (start_day + timedelta(days=i)).date().isoformat()
        buckets[d] = {"date": d, "ratings": [], "scores": [], "counts": {"Positive": 0, "Neutral": 0, "Negative": 0}}

    for r in reviews:
        dt = _parse_review_date(r)
        if not dt or dt < start_day or dt > end_day:
            continue
        day_str = dt.date().isoformat()
        lbl = classify_sentiment(r.rating)
        score = 1.0 if lbl == "Positive" else -1.0 if lbl == "Negative" else 0.0
        buckets[day_str]["ratings"].append(r.rating or 0)
        buckets[day_str]["scores"].append(score)
        buckets[day_str]["counts"][lbl] += 1

    return [
        {
            "date": d,
            "avg_rating": round(sum(b["ratings"]) / len(b["ratings"]), 2) if b["ratings"] else None,
            "sent_score": round(sum(b["scores"]) / len(b["scores"]), 3) if b["scores"] else 0.0,
            **b["counts"]
        }
        for d, b in sorted(buckets.items())
    ]

def get_review_summary_data(
    reviews: List[Review],
    company: Company,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Single-fetch summary for a given company and date window.
    Includes: totals, avg rating, sentiments, monthly trend, day-wise series,
    risk score/level, and AI recommendations derived from negative tokens.
    """
    now = datetime.now(timezone.utc)
    start = start or (now - timedelta(days=180))  # Default: last 6 months
    end = end or now
    if end < start:
        start, end = end, start

    windowed = [
        r for r in reviews
        if (dt := _parse_review_date(r)) and start <= dt <= end
    ]

    if not windowed:
        return {
            "company_name": getattr(company, "name", f"ID {company.id}"),
            "total_reviews": 0,
            "avg_rating": 0.0,
            "risk_score": 0,
            "risk_level": "Low",
            "trend_data": [],
            "trend": {"signal": "insufficient_data", "delta": 0.0},
            "sentiments": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "ai_recommendations": [],
            "daily_series": [],
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "payload_version": "3.2"
        }

    sentiments: Dict[str, int] = {"Positive": 0, "Neutral": 0, "Negative": 0}
    trend_data: Dict[str, List[float]] = defaultdict(list)
    neg_keywords: List[str] = []

    for r in windowed:
        sent = classify_sentiment(r.rating)
        sentiments[sent] += 1
        if sent == "Negative" and r.text:
            neg_keywords.extend(extract_keywords(r.text))
        dt = _parse_review_date(r)
        if dt:
            trend_data[dt.strftime("%Y-%m")].append(r.rating or 0)

    trend_list = [
        {"month": m, "avg_rating": round(sum(v)/len(v), 2)}
        for m, v in sorted(trend_data.items())
    ]

    # Trend signal from monthly buckets
    trend = {"signal": "insufficient_data", "delta": 0.0}
    if len(trend_list) >= 3:
        last = trend_list[-1]["avg_rating"]
        first = trend_list[0]["avg_rating"]
        delta = round(last - first, 2)
        if len(trend_list) >= 6:
            last3 = sum(x["avg_rating"] for x in trend_list[-3:]) / 3
            prev3 = sum(x["avg_rating"] for x in trend_list[-6:-3]) / 3 if len(trend_list) >= 6 else last3
            delta = round(last3 - prev3, 2)
        if delta <= -0.3:
            trend = {"signal": "declining", "delta": delta}
        elif delta >= 0.3:
            trend = {"signal": "improving", "delta": delta}
        else:
            trend = {"signal": "stable", "delta": delta}

    total = len(windowed)
    rated = [r.rating for r in windowed if r.rating is not None]
    avg_rating = round(sum(rated)/len(rated), 2) if rated else 0.0

    neg_share = sentiments["Negative"] / total if total else 0
    risk_score = round(neg_share * 100 + (15 if trend["signal"] == "declining" else 0), 1)
    risk_level = "High" if risk_score >= 45 else "Medium" if risk_score >= 20 else "Low"

    recs = []
    seen = set()
    for kw, count in Counter(neg_keywords).most_common(6):
        if kw in seen:
            continue
        seen.add(kw)
        recs.append({
            "area": kw,
            "count": count,
            "priority": "High" if count >= 5 else "Medium",
            "action": _action_for_keyword(kw)
        })

    daily_series = _daily_buckets_range(windowed, start, end)

    return {
        "company_name": getattr(company, "name", f"ID {company.id}"),
        "total_reviews": total,
        "avg_rating": avg_rating,
        "sentiments": sentiments,
        "trend_data": trend_list,
        "trend": trend,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "ai_recommendations": recs,
        "daily_series": daily_series,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "payload_version": "3.2"
    }

# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────
@router.get("/google/places")
def google_places_search(q: str = Query(..., min_length=2)):
    """
    Search Google Places; returns candidates enriched with city/country/website/phone/rating
    by calling Places Details for each candidate (best-effort).
    """
    if not gmaps:
        return {"ok": False, "reason": "Google Places client not available"}
    try:
        resp = gmaps.find_place(
            input=q,
            input_type="textquery",
            fields=["place_id", "name", "formatted_address"]
        )
        candidates = (resp.get("candidates") or [])[:5]
        items = []
        for c in candidates:
            pid = c.get("place_id")
            detail = _enrich_place_detail(pid) if pid else {}
            items.append({
                "name": detail.get("name") or c.get("name"),
                "place_id": pid,
                "formatted_address": detail.get("formatted_address") or c.get("formatted_address"),
                "city": detail.get("city"),
                "country": detail.get("country"),
                "rating": detail.get("rating"),
                "user_ratings_total": detail.get("user_ratings_total"),
                "location": detail.get("location"),
                "website": detail.get("website"),
                "international_phone_number": detail.get("international_phone_number"),
            })
        return {"ok": True, "items": items}
    except Exception as e:
        logger.error(f"Places search failed: {e}")
        return {"ok": False, "reason": "external_api_error"}

@router.get("/company/{company_id}/google_details")
def google_details_for_company(company_id: int, db: Session = Depends(get_db)):
    """
    Fetch live Google attributes for the company's place_id and (best-effort) update DB fields.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    if not gmaps or not company.place_id:
        return {"ok": False, "reason": "missing place_id or Google client"}

    detail = _enrich_place_detail(company.place_id)
    refreshed = False

    try:
        updates = {}
        if detail.get("rating") is not None and hasattr(company, "google_rating"):
            updates["google_rating"] = detail["rating"]
        if detail.get("user_ratings_total") is not None and hasattr(company, "user_ratings_total"):
            updates["user_ratings_total"] = detail["user_ratings_total"]
        if detail.get("website") and hasattr(company, "website"):
            updates["website"] = detail["website"]
        if (city := detail.get("city")) or (country := detail.get("country")):
            loc = ", ".join(filter(None, [city, country]))
            if loc and hasattr(company, "location"):
                updates["location"] = loc

        if updates:
            for k, v in updates.items():
                setattr(company, k, v)
            db.commit()
            refreshed = True
    except Exception as e:
        logger.warning(f"Company update failed: {e}")

    return {"ok": True, "refreshed": refreshed, "details": detail}

@router.post("/company")
def add_company(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization")
):
    """
    Create a new company by name + place_id.
    If API_TOKEN is set, validates token via X-API-Key or Authorization Bearer.
    Enriches company fields via Google details (best-effort).
    """
    if API_TOKEN:
        token = (x_api_key or "").strip() or ""
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if token != API_TOKEN:
            raise HTTPException(401, "Invalid API token")

    name = (payload.get("name") or "").strip()
    place_id = (payload.get("place_id") or "").strip()
    if not name or not place_id:
        raise HTTPException(422, "name and place_id required")

    if db.query(Company).filter(Company.name.ilike(name)).first():
        raise HTTPException(409, "Company name already exists")
    if db.query(Company).filter(Company.place_id == place_id).first():
        raise HTTPException(409, "Place ID already registered")

    company = Company(name=name, place_id=place_id)
    # Accept optional provided values; may be overwritten by enrich below.
    if hasattr(company, "website"):
        company.website = (payload.get("website") or "").strip() or None
    if hasattr(company, "location"):
        company.location = (payload.get("location") or "").strip() or None

    db.add(company)
    db.commit()
    db.refresh(company)

    # Enrich from Google if possible
    if gmaps and place_id:
        detail = _enrich_place_detail(place_id)
        if detail:
            updates = {}
            if detail.get("website") and hasattr(company, "website"):
                updates["website"] = detail["website"]
            if detail.get("city") or detail.get("country"):
                loc = ", ".join(filter(None, [detail.get("city"), detail.get("country")]))
                if loc and hasattr(company, "location"):
                    updates["location"] = loc
            if hasattr(company, "google_rating") and detail.get("rating") is not None:
                updates["google_rating"] = detail["rating"]
            if hasattr(company, "user_ratings_total") and detail.get("user_ratings_total") is not None:
                updates["user_ratings_total"] = detail["user_ratings_total"]

            if updates:
                for k, v in updates.items():
                    setattr(company, k, v)
                db.commit()

    return {"ok": True, "company_id": company.id}

@router.get("/summary/{company_id}")
def reviews_summary(
    company_id: int,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Single-fetch summary for a company over a date range (?start=&end=).
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    start_dt = _parse_date_param(start, as_end=False) if start else None
    end_dt = _parse_date_param(end, as_end=True) if end else None

    # Filter directly in database
    query = db.query(Review).filter(Review.company_id == company_id)
    if start_dt:
        query = query.filter(Review.review_date >= start_dt)
    if end_dt:
        query = query.filter(Review.review_date <= end_dt)

    # Safety cap
    reviews = query.order_by(Review.review_date.desc()).limit(8000).all()
    return get_review_summary_data(reviews, company, start_dt, end_dt)

@router.get("/sync/{company_id}")
def reviews_sync(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    if not gmaps:
        return {"ok": False, "reason": "Google client unavailable"}

    added = fetch_and_save_reviews_places(company, db)
    return {"ok": True, "added": added, "message": "Sync completed"}

@router.get("/diagnostics")
def reviews_diagnostics():
    return {
        "googlemaps_imported": googlemaps is not None,
        "places_client_active": gmaps is not None,
        "api_key_source": api_src,
        "api_token_configured": bool(API_TOKEN),
        "default_window_days": 180
    }
