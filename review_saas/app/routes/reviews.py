# FILE: review_saas/app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Depends, Header, Query
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

import os
import re
import logging

# Optional Google client
try:
    import googlemaps
except Exception:
    googlemaps = None

logger = logging.getLogger("reviews")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/reviews", tags=["reviews"])

# ---------------- Config ----------------
def _resolve_places_api_key() -> Tuple[Optional[str], str]:
    key = os.getenv("GOOGLE_PLACES_API_KEY")
    if key:
        return key, "GOOGLE_PLACES_API_KEY"
    alt = os.getenv("GOOGLE_MAPS_API_KEY")
    if alt:
        logger.warning("Falling back to GOOGLE_MAPS_API_KEY for Places.")
        return alt, "GOOGLE_MAPS_API_KEY"
    return None, "NONE"

api_key, api_src = _resolve_places_api_key()
gmaps = None
if api_key and googlemaps:
    try:
        gmaps = googlemaps.Client(key=api_key)
        logger.info(f"Google Places client initialized using {api_src}")
    except Exception as e:
        logger.warning(f"Failed to initialize Google Maps client: {e}")

API_TOKEN = os.getenv("API_TOKEN")
FIXED_DEFAULT_START = datetime(2026, 2, 21, tzinfo=timezone.utc)

# ---------------- NLP helpers ----------------
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

def _score_from_sentiment(lbl: str) -> float:
    if lbl == "Positive": return 1.0
    if lbl == "Negative": return -1.0
    return 0.0

# ---------------- Date parsing ----------------
_DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y", "%Y.%m.%d",
    "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
]
def _parse_date_param(val: Optional[str], *, as_end: bool=False) -> Optional[datetime]:
    if not val: return None
    s = val.strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            dt = dt.replace(tzinfo=timezone.utc) if not dt.tzinfo else dt.astimezone(timezone.utc)
            if "T" not in fmt:
                dt = dt.replace(hour=23, minute=59, second=59, microsecond=0) if as_end else dt.replace(hour=0, minute=0, second=0, microsecond=0)
            return dt
        except Exception:
            continue
    raise HTTPException(status_code=422, detail="Invalid date format")

# ---------------- DB helpers ----------------
def _preload_existing_keys(db: Session, company_id: int):
    existing = db.query(Review).filter(Review.company_id == company_id).all()
    return {(r.text, r.rating, r.review_date) for r in existing}

def fetch_and_save_reviews_places(company: Company, db: Session, max_reviews: int = 50) -> int:
    if not gmaps or not getattr(company, "place_id", None):
        return 0
    existing_keys = _preload_existing_keys(db, company.id)
    result = gmaps.place(place_id=company.place_id, fields=["reviews","rating","user_ratings_total"]).get("result", {})
    reviews_data = (result.get("reviews", []) or [])[:max_reviews]
    added = 0
    for rev in reviews_data:
        review_date = datetime.fromtimestamp(rev["time"], tz=timezone.utc) if rev.get("time") else None
        key = (rev.get("text",""), rev.get("rating"), review_date)
        if key in existing_keys: continue
        db.add(Review(
            company_id=company.id, text=key[0], rating=key[1],
            reviewer_name=rev.get("author_name","Anonymous"),
            review_date=review_date, fetch_at=datetime.now(timezone.utc)
        ))
        added += 1
    if added: db.commit()
    if hasattr(company, "google_rating"): company.google_rating = result.get("rating")
    if hasattr(company, "user_ratings_total"): company.user_ratings_total = result.get("user_ratings_total")
    db.commit()
    return added

# ---------------- Analysis ----------------
def _detect_trend(trend_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(trend_data) < 3: return {"signal":"insufficient_data","delta":0.0}
    data = sorted(trend_data, key=lambda x: x["month"])
    if len(data) == 3:
        delta = round(data[-1]["avg_rating"] - data[0]["avg_rating"], 2)
    else:
        last3 = data[-3:]; prev3 = data[-6:-3]
        last_avg = sum(x["avg_rating"] for x in last3)/3
        prev_avg = sum(x["avg_rating"] for x in prev3)/3 if prev3 else last_avg
        delta = round(last_avg-prev_avg,2)
    if delta <= -0.3: return {"signal":"declining","delta":delta}
    if delta >= 0.3: return {"signal":"improving","delta":delta}
    return {"signal":"stable","delta":delta}

def _daily_buckets_range(reviews: List[Review], start: datetime, end: datetime) -> List[Dict[str, Any]]:
    start_day = start.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end_day = end.replace(hour=23, minute=59, second=59, microsecond=0, tzinfo=timezone.utc)
    days = (end_day.date() - start_day.date()).days + 1
    if days < 1: return []
    buckets: Dict[str, Dict[str, Any]] = {}
    for i in range(days):
        d = (start_day + timedelta(days=i)).date().isoformat()
        buckets[d] = {"date": d, "ratings": [], "scores": [], "counts":{"Positive":0,"Neutral":0,"Negative":0}}
    for r in reviews:
        dt = _parse_review_date(r)
        if not dt or dt < start_day or dt > end_day: continue
        d = dt.date().isoformat()
        lbl = classify_sentiment(r.rating); sc = _score_from_sentiment(lbl)
        buckets[d]["ratings"].append(r.rating or 0)
        buckets[d]["scores"].append(sc)
        buckets[d]["counts"][lbl] += 1
    series = []
    for d in sorted(buckets.keys()):
        rs = buckets[d]["ratings"]; ss = buckets[d]["scores"]; c = buckets[d]["counts"]
        series.append({
            "date": d,
            "avg_rating": round(sum(rs)/len(rs), 2) if rs else None,
            "sent_score": round(sum(ss)/len(ss), 3) if ss else 0.0,
            "positive": c["Positive"], "neutral": c["Neutral"], "negative": c["Negative"]
        })
    return series

def get_review_summary_data(
    reviews: List[Review], company: Company,
    start_override: Optional[datetime] = None, end_override: Optional[datetime] = None
):
    start = start_override or FIXED_DEFAULT_START
    end = end_override or datetime.now(timezone.utc)
    if end < start: start, end = end, start

    windowed = []
    for r in reviews:
        r_dt = _parse_review_date(r)
        if r_dt and start <= r_dt <= end:
            windowed.append(r)

    if not windowed:
        return {
            "company_name": getattr(company, "name", f"Company {getattr(company,'id','')}"),
            "total_reviews": 0, "avg_rating": 0.0,
            "risk_score": 0, "risk_level":"Low",
            "trend_data": [], "trend":{"signal":"insufficient_data","delta":0.0},
            "sentiments":{"Positive":0,"Neutral":0,"Negative":0},
            "ai_recommendations": [], "reviews": [],
            "daily_series": [], "window":{"start": start.isoformat(), "end": end.isoformat()},
            "payload_version":"3.0"
        }

    sentiments = {"Positive":0,"Neutral":0,"Negative":0}
    trend_data: Dict[str, List[float]] = defaultdict(list)
    neg_tokens: List[str] = []
    for r in windowed:
        s = classify_sentiment(r.rating)
        sentiments[s]+=1
        tokens = extract_keywords(r.text)
        if s == "Negative": neg_tokens.extend(tokens)
        r_dt = _parse_review_date(r)
        if r_dt: trend_data[r_dt.strftime("%Y-%m")].append(r.rating or 0)

    trend_list = [{"month":m,"avg_rating":round(sum(v)/len(v),2)} for m,v in sorted(trend_data.items())]
    trend_signal = _detect_trend(trend_list)
    total = len(windowed)
    rated = [r.rating for r in windowed if r.rating is not None]
    avg = round(sum(rated)/len(rated),2) if rated else 0.0
    neg_share = sentiments["Negative"]/total if total else 0
    risk_score = round(neg_share*100 + (10 if trend_signal["signal"]=="declining" else 0),2)
    risk_level = "High" if risk_score>=40 else "Medium" if risk_score>=20 else "Low"

    from collections import Counter
    recs = []
    seen=set()
    for kw,count in Counter(neg_tokens).most_common(5):
        if kw in seen: continue
        seen.add(kw)
        recs.append({"area":kw,"priority":"High" if count>=5 else "Medium","action":_action_for_keyword(kw)})

    daily_series = _daily_buckets_range(windowed, start, end)

    return {
        "company_name": getattr(company, "name", f"Company {getattr(company,'id','')}"),
        "total_reviews": total, "avg_rating": avg,
        "sentiments": sentiments, "trend_data": trend_list, "trend": trend_signal,
        "risk_score": risk_score, "risk_level": risk_level,
        "ai_recommendations": recs,
        "daily_series": daily_series,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "payload_version": "3.0"
    }

# ---------------- Enrichment helpers (Google) ----------------
def _city_country_from_components(components: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    city = country = None
    for comp in components or []:
        types = comp.get("types", [])
        if "locality" in types or "postal_town" in types or "administrative_area_level_2" in types:
            city = city or comp.get("long_name")
        if "country" in types:
            country = comp.get("long_name")
    return city, country

def _enrich_place_detail(place_id: str) -> Dict[str, Any]:
    if not gmaps: return {}
    try:
        fields = [
            "name","place_id","formatted_address","address_components","website",
            "international_phone_number","rating","user_ratings_total",
            "geometry","opening_hours"
        ]
        res = gmaps.place(place_id=place_id, fields=fields).get("result", {}) or {}
        city, country = _city_country_from_components(res.get("address_components") or [])
        loc = (res.get("geometry") or {}).get("location") or {}
        return {
            "name": res.get("name"),
            "place_id": res.get("place_id"),
            "formatted_address": res.get("formatted_address"),
            "city": city, "country": country,
            "website": res.get("website"),
            "international_phone_number": res.get("international_phone_number"),
            "rating": res.get("rating"),
            "user_ratings_total": res.get("user_ratings_total"),
            "location": {"lat": loc.get("lat"), "lng": loc.get("lng")},
            "opening_hours": {"weekday_text": (res.get("opening_hours") or {}).get("weekday_text")}
        }
    except Exception as e:
        logger.error(f"enrich_place_detail failed: {e}")
        return {}

# ---------------- New endpoints (Google search & details) ----------------
@router.get("/google/places")
def google_places_search(q: str = Query(..., min_length=2)):
    if not gmaps:
        return {"ok": False, "reason": "Google client not initialized"}
    try:
        resp = gmaps.find_place(input=q, input_type="textquery", fields=["place_id","name","formatted_address"])
        candidates = (resp.get("candidates") or [])[:5]
        items = []
        for c in candidates:
            pid = c.get("place_id")
            detail = _enrich_place_detail(pid) if pid else {}
            # fallback to basic values if details fail
            items.append({
                "name": detail.get("name") or c.get("name"),
                "place_id": pid,
                "formatted_address": detail.get("formatted_address") or c.get("formatted_address"),
                "city": detail.get("city"),
                "country": detail.get("country"),
                "website": detail.get("website"),
                "international_phone_number": detail.get("international_phone_number"),
                "rating": detail.get("rating"),
                "user_ratings_total": detail.get("user_ratings_total"),
                "location": detail.get("location"),
            })
        return {"ok": True, "items": items}
    except Exception as e:
        logger.error(f"Places search failed: {e}")
        return {"ok": False, "reason": "places_search_failed"}

@router.get("/company/{company_id}/google_details")
def google_details_for_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if not gmaps or not getattr(company, "place_id", None):
        return {"ok": False, "reason": "missing_google_or_place_id"}
    detail = _enrich_place_detail(company.place_id)
    # Update DB fields if present
    try:
        if hasattr(company, "google_rating"): company.google_rating = detail.get("rating")
        if hasattr(company, "user_ratings_total"): company.user_ratings_total = detail.get("user_ratings_total")
        if hasattr(company, "website") and detail.get("website"): company.website = detail["website"]
        if hasattr(company, "location"):
            city = detail.get("city"); country = detail.get("country")
            if city or country:
                company.location = ", ".join([p for p in [city, country] if p])
        db.commit()
        refreshed = True
    except Exception as e:
        logger.warning(f"DB update skipped/failed: {e}")
        refreshed = False
    return {"ok": True, "refreshed": refreshed, "details": detail}

# ---------------- Create company (secured if API_TOKEN set) ----------------
def _validate_api_token(x_api_key: Optional[str], auth: Optional[str]):
    if not API_TOKEN:
        return  # token not configured; allow open (your choice)
    token = None
    if x_api_key: token = x_api_key.strip()
    elif auth and auth.lower().startswith("bearer "): token = auth[7:].strip()
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API token")

@router.post("/company")
def add_company(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization")
):
    _validate_api_token(x_api_key, authorization)

    name = (payload.get("name") or "").strip()
    place_id = (payload.get("place_id") or "").strip() or None
    website = (payload.get("website") or "").strip() or None
    location = (payload.get("location") or "").strip() or None

    if not name or not place_id:
        raise HTTPException(status_code=422, detail="name and place_id are required")

    existing = db.query(Company).filter(Company.name.ilike(name)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Company with same name already exists")
    dup = db.query(Company).filter(Company.place_id == place_id).first() if hasattr(Company, "place_id") else None
    if dup:
        raise HTTPException(status_code=409, detail="Company with same place_id already exists")

    company = Company(name=name)
    if hasattr(company, "place_id"): company.place_id = place_id
    if hasattr(company, "website"): company.website = website
    if hasattr(company, "location"): company.location = location
    db.add(company); db.commit(); db.refresh(company)

    # optional: prefill rating/phone/address via details
    detail = _enrich_place_detail(place_id) if gmaps else {}
    try:
        if hasattr(company, "google_rating"): company.google_rating = detail.get("rating")
        if hasattr(company, "user_ratings_total"): company.user_ratings_total = detail.get("user_ratings_total")
        if hasattr(company, "website") and detail.get("website"): company.website = detail["website"]
        if hasattr(company, "location"):
            city = detail.get("city"); country = detail.get("country")
            if city or country:
                company.location = ", ".join([p for p in [city, country] if p])
        db.commit()
    except Exception as e:
        logger.warning(f"prefill enrich failed: {e}")

    return {"ok": True, "company_id": company.id}

# ---------------- Existing endpoints ----------------
@router.get("/summary/{company_id}")
def reviews_summary(
    company_id: int,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    start_dt = _parse_date_param(start, as_end=False) if start else None
    end_dt = _parse_date_param(end, as_end=True) if end else None
    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    return get_review_summary_data(reviews, company, start_dt, end_dt)

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
        "places_client_initialized": gmaps is not None
    }
