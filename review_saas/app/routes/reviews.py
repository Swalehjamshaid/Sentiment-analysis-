# File: review_saas/app/routes/reviews.py

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

import os
import re
import logging

# Google Maps is optional; we will degrade gracefully if no key is provided
try:
    import googlemaps
except Exception:  # pragma: no cover
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
# Google Maps API Client (optional)
# ─────────────────────────────────────────────────────────────
api_key = os.getenv("GOOGLE_PLACES_API_KEY")
gmaps = None
if api_key and googlemaps is not None:
    try:
        gmaps = googlemaps.Client(key=api_key)
    except Exception as e:
        logger.warning(f"Failed to initialize Google Maps client: {e}")
else:
    if not api_key:
        logger.warning("Google Places API Key not set; /reviews fetch will be disabled.")
    if googlemaps is None:
        logger.warning("googlemaps package not available; /reviews fetch will be disabled.")

# ─────────────────────────────────────────────────────────────
# Default Reference Date (last 180 days unless overridden)
# ─────────────────────────────────────────────────────────────
DEFAULT_DATE_FROM = datetime.now(timezone.utc) - timedelta(days=180)

# ─────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────
def classify_sentiment(rating: Optional[float]) -> str:
    """Simple rating-based sentiment classifier."""
    if rating is None:
        return "Neutral"
    if rating >= 4:
        return "Positive"
    if rating == 3:
        return "Neutral"
    return "Negative"


def extract_keywords(text: Optional[str]) -> List[str]:
    """Very lightweight keyword extractor: lowercase, strip punctuation, drop stopwords and small tokens."""
    if not text:
        return []
    text = re.sub(r"[^\w\s]", "", text.lower())
    stopwords = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "the", "this", "is", "it", "to", "with", "was", "of", "in", "on",
        "or", "we", "you", "our", "your", "but", "not", "they", "them",
    }
    return [w for w in text.split() if w not in stopwords and len(w) > 2]


# Map keywords (or substrings) to suggested actions
ACTION_MAP: Dict[str, str] = {
    # Service & speed
    "wait": "Optimize peak-hour staffing and enable queue management to reduce waiting times.",
    "slow": "Introduce service SLAs and staff cross-training to speed up fulfillment.",
    "service": "Launch a service excellence workshop and implement a QA checklist.",
    "attitude": "Coach frontline staff on tone, empathy, and recovery scripts.",
    # Pricing & value
    "price": "Review pricing strategy vs competitors and introduce transparent offers.",
    "expensive": "Consider tiered pricing, bundles, or value-add to offset price sensitivity.",
    "overpriced": "Run a competitive pricing audit and publish price-matching policy.",
    # Cleanliness & hygiene
    "clean": "Increase cleanliness checks and janitorial frequency with checklists.",
    "dirty": "Run a deep-clean schedule; assign daily ownership and spot checks.",
    # Quality & product
    "quality": "Audit suppliers and batch QA; implement defect capture & feedback loop.",
    "defect": "Add incoming QC and RMA triage to reduce defect recurrence.",
    "taste": "Run blind A/B tests and calibrate recipes / sourcing.",
    # Availability & stock
    "stock": "Improve demand forecasting; set minimum stock alerts for fast-movers.",
    "availability": "Share stockout dashboards and add substitutions / backorder flows.",
    # Environment
    "noise": "Introduce quiet hours / acoustic dampening, and seat zoning.",
    "crowd": "Implement reservation windows and dynamic staffing for peak periods.",
    # Payment & digital
    "payment": "Add more payment options and reliability monitoring for terminals.",
    "app": "Improve app reliability, add in-app feedback capture for crashes.",
    # Generic fallback
    "rude": "Reinforce code-of-conduct and coaching with role-play and audits.",
    "manager": "Increase manager-on-duty coverage and escalation visibility.",
}


def _action_for_keyword(keyword: str) -> str:
    """Return the best-matching action based on substring matching, else default guidance."""
    k = keyword.lower()
    for needle, action in ACTION_MAP.items():
        if needle in k:
            return action
    return "Conduct root-cause analysis and monitor sentiment trends; run a 5-Whys workshop."


def _parse_review_date(r: Review) -> Optional[datetime]:
    """Ensure review_date is datetime with timezone (UTC)."""
    if not getattr(r, "review_date", None):
        return None
    if isinstance(r.review_date, datetime):
        # Normalize to UTC if tz-aware, else assume UTC
        return r.review_date.astimezone(timezone.utc) if r.review_date.tzinfo else r.review_date.replace(tzinfo=timezone.utc)
    # If it's a date object
    return datetime.combine(r.review_date, datetime.min.time(), tzinfo=timezone.utc)


def _get_date_window() -> Tuple[datetime, datetime]:
    """Read inclusive date window from env, defaults to last 180 days."""
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
    # Normalize ordering
    if end < start:
        start, end = end, start
    return start, end


def _format_suggested_reply(sentiment: str, reviewer_name: str, keywords: List[str]) -> str:
    """Generate a simple, non-controversial reply template based on sentiment and topics."""
    name = reviewer_name or "there"
    topic = (", ".join(sorted(set(keywords[:3])))) if keywords else "your experience"
    if sentiment == "Positive":
        return f"Hi {name}, thanks for the great rating! We're glad you enjoyed {topic}. See you again!"
    if sentiment == "Neutral":
        return f"Hi {name}, thanks for your feedback. We’ll use your input about {topic} to improve."
    # Negative
    return (
        f"Hi {name}, we're sorry about the issues with {topic}. "
        f"Please DM us so we can make this right and prevent it in the future."
    )


def _detect_trend(trend_data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Detect rating trend over time: looks at last 3 months vs previous 3 months average.
    Returns a signal with direction and magnitude.
    """
    if len(trend_data_list) < 3:
        return {"signal": "insufficient_data", "delta": 0.0, "note": "Less than 3 months of data"}
    # Sort by month field "YYYY-MM"
    data = sorted(trend_data_list, key=lambda x: x["month"])
    last3 = data[-3:]
    prev3 = data[-6:-3] if len(data) >= 6 else []
    last_avg = sum(x["avg_rating"] for x in last3) / len(last3)
    prev_avg = sum(x["avg_rating"] for x in prev3) / len(prev3) if prev3 else last_avg
    delta = round(last_avg - prev_avg, 2)
    if delta <= -0.3:
        return {"signal": "declining", "delta": delta, "note": "Recent ratings down vs earlier window"}
    if delta >= 0.3:
        return {"signal": "improving", "delta": delta, "note": "Recent ratings up vs earlier window"}
    return {"signal": "stable", "delta": delta, "note": "No material change in trend"}


def _priority_from_counts(mentions: int, neg_share: float) -> str:
    """Heuristic priority based on mentions volume and negative share."""
    if mentions >= 5 or neg_share >= 0.35:
        return "High"
    if mentions >= 3 or neg_share >= 0.25:
        return "Medium"
    return "Low"


def _risk_level(score: float) -> str:
    """Translate risk score (0-100) to qualitative level."""
    if score >= 40:
        return "High"
    if score >= 20:
        return "Medium"
    return "Low"


def _generate_ai_recommendations(
    sentiments: Dict[str, int],
    neg_kw_counter: Counter,
    trend_signal: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Produce actionable recommendations derived from:
      - Negative keyword frequency (issues)
      - Overall negative share
      - Trend direction (declining/stable/improving)
    """
    total = sum(sentiments.values()) or 1
    neg_share = sentiments.get("Negative", 0) / total

    recs: List[Dict[str, Any]] = []
    for keyword, mentions in neg_kw_counter.most_common(8):
        action = _action_for_keyword(keyword)
        recs.append({
            "weak_area": keyword,
            "issue_mentions": mentions,
            "priority": _priority_from_counts(mentions, neg_share),
            "recommended_action": action,
            "rationale": (
                f"Keyword '{keyword}' appears {mentions}× in negative reviews; "
                f"overall negative share = {round(neg_share*100, 1)}%."
            ),
            "owner": "Ops Lead",
            "timeframe": "2-4 weeks",
            "kpi": "Reduce mentions of '{keyword}' by 50% and lift avg rating by +0.2 in 60 days",
            "expected_outcome": "Improved customer satisfaction and reduced churn.",
        })

    # Trend-based meta recommendation
    sig = trend_signal.get("signal")
    delta = trend_signal.get("delta", 0.0)
    if sig == "declining":
        recs.insert(0, {
            "weak_area": "trend_decline",
            "issue_mentions": None,
            "priority": "High",
            "recommended_action": "Launch a rapid response program: daily QA huddles, incident review, and on-shift coaching.",
            "rationale": f"Ratings are declining ({delta}). Mitigate quickly to prevent compounding impact.",
            "owner": "GM + QA",
            "timeframe": "Immediate (1-2 weeks)",
            "kpi": "Stabilize trend within 14 days; +0.3 rating delta in next 30 days",
            "expected_outcome": "Arrest decline and restore confidence.",
        })
    elif sig == "improving":
        recs.append({
            "weak_area": "trend_improvement",
            "issue_mentions": None,
            "priority": "Low",
            "recommended_action": "Double down on what works: recognize top performers and codify best practices.",
            "rationale": f"Ratings are improving ({delta}). Preserve momentum.",
            "owner": "GM",
            "timeframe": "30-45 days",
            "kpi": "Sustain +0.3 delta for the next quarter",
            "expected_outcome": "Compounded gains in satisfaction and loyalty.",
        })

    return recs


# ─────────────────────────────────────────────────────────────
# Fetch reviews from Google API and store
# ─────────────────────────────────────────────────────────────
def fetch_and_save_reviews(company: Company, db: Session, max_reviews: int = 50) -> int:
    """
    Pull Google reviews (if API available) and upsert into DB.
    Returns number of new reviews added.
    """
    if not gmaps:
        logger.info("Google client unavailable; skipping fetch.")
        return 0
    if not getattr(company, "place_id", None):
        return 0

    try:
        result = gmaps.place(
            place_id=company.place_id,
            fields=["reviews", "rating", "user_ratings_total"]
        ).get("result", {})

        reviews_data = (result.get("reviews", []) or [])[:max_reviews]
        added_count = 0

        for rev in reviews_data:
            rev_time = rev.get("time")
            review_date = datetime.fromtimestamp(rev_time, tz=timezone.utc) if rev_time else None

            # Dedup heuristic
            exists = db.query(Review).filter(
                Review.company_id == company.id,
                Review.text == rev.get("text", ""),
                Review.rating == rev.get("rating"),
                Review.review_date == review_date
            ).first()
            if exists:
                continue

            db.add(Review(
                company_id=company.id,
                text=rev.get("text", ""),
                rating=rev.get("rating"),
                reviewer_name=rev.get("author_name", "Anonymous"),
                review_date=review_date,
                fetch_at=datetime.now(timezone.utc)
            ))
            added_count += 1

        # Update company aggregates if present
        if "rating" in result:
            company.google_rating = result["rating"]
        if "user_ratings_total" in result:
            company.user_ratings_total = result["user_ratings_total"]

        if added_count > 0:
            db.commit()

        return added_count

    except Exception as e:
        logger.error(f"Error fetching reviews for company {company.id}: {e}")
        return 0


# ─────────────────────────────────────────────────────────────
# Core Analysis Function
# ─────────────────────────────────────────────────────────────
def get_review_summary_data(reviews: List[Review], company: Company) -> Dict[str, Any]:
    start_date, end_date = _get_date_window()

    # Window to requested period
    windowed_reviews = [
        r for r in reviews
        if (_parse_review_date(r) and start_date <= _parse_review_date(r) <= end_date)
    ]

    if not windowed_reviews:
        return {
            "company_name": company.name,
            "google_rating": getattr(company, "google_rating", 0),
            "google_total_ratings": getattr(company, "user_ratings_total", 0),
            "total_reviews": 0,
            "avg_rating": 0.0,
            "sentiments": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "positive_keywords": [],
            "negative_keywords": [],
            "trend_data": [],
            "weak_areas": [],
            "strength_areas": [],
            "ai_recommendations": [],
            "risk_score": 0.0,
            "risk_level": "Low",
            "ai_observations": {"trend": {"signal": "insufficient_data", "delta": 0.0}},
            "reviews": []
        }

    # Basic metrics
    total_reviews = len(windowed_reviews)
    ratings = [r.rating for r in windowed_reviews if r.rating is not None]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0

    # Sentiment & keyword mining
    sentiments = {"Positive": 0, "Neutral": 0, "Negative": 0}
    pos_keywords: List[str] = []
    neg_keywords: List[str] = []
    trend_data = defaultdict(list)
    reviews_list: List[Dict[str, Any]] = []

    for r in windowed_reviews:
        r_dt = _parse_review_date(r)
        sentiment = classify_sentiment(r.rating)
        sentiments[sentiment] += 1

        kws = extract_keywords(r.text)
        if sentiment == "Positive":
            pos_keywords.extend(kws)
        elif sentiment == "Negative":
            neg_keywords.extend(kws)

        if r_dt:
            trend_data[r_dt.strftime("%Y-%m")].append(r.rating or 0)

        reviews_list.append({
            "id": r.id,
            "review_text": r.text or "",
            "rating": r.rating,
            "reviewer_name": r.reviewer_name or "Anonymous",
            "review_date": r_dt.isoformat() if r_dt else None,
            "sentiment": sentiment,
            "suggested_reply": _format_suggested_reply(sentiment, r.reviewer_name or "there", kws),
        })

    # Monthly trend analysis
    trend_data_list = [
        {"month": m, "avg_rating": round(sum(v) / len(v), 2), "count": len(v)}
        for m, v in sorted(trend_data.items())
        if v
    ]

    # Top keyword sets
    pos_counter = Counter(pos_keywords)
    neg_counter = Counter(neg_keywords)

    top_positive = [{"keyword": k, "mentions": v} for k, v in pos_counter.most_common(8)]
    top_negative = [{"keyword": k, "mentions": v} for k, v in neg_counter.most_common(8)]

    # Trend signal
    trend_signal = _detect_trend(trend_data_list)

    # AI-style recommendations
    ai_recs = _generate_ai_recommendations(sentiments, neg_counter, trend_signal)

    # Risk score: share of negatives (0-100)
    risk_score = round((sentiments["Negative"] / total_reviews) * 100, 2)
    risk_level = _risk_level(risk_score)

    return {
        "company_name": company.name,
        "google_rating": getattr(company, "google_rating", 0),
        "google_total_ratings": getattr(company, "user_ratings_total", 0),
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "sentiments": sentiments,
        "positive_keywords": [k for k, _ in pos_counter.most_common(8)],
        "negative_keywords": top_negative,  # list of dicts for detail
        "trend_data": trend_data_list,
        "weak_areas": top_negative,
        "strength_areas": top_positive,
        "ai_recommendations": ai_recs,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "ai_observations": {"trend": trend_signal},
        "reviews": sorted(reviews_list, key=lambda x: (x["review_date"] or ""), reverse=True)[:15]
    }


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────
@router.get("/summary/{company_id}")
def reviews_summary(company_id: int, refresh: bool = False, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Optional refresh from Google
    if refresh:
        # Allow env to override how many we pull per refresh
        max_reviews = int(os.getenv("GOOGLE_REVIEWS_PULL_LIMIT", "50"))
        fetch_and_save_reviews(company, db, max_reviews=max_reviews)

    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    return get_review_summary_data(reviews, company)


@router.get("/my-companies")
def get_my_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).all()
    return [{"id": c.id, "name": c.name, "city": getattr(c, "city", "N/A")} for c in companies]


@router.get("/recommendations/{company_id}")
def reviews_recommendations(company_id: int, db: Session = Depends(get_db)):
    """
    Convenience endpoint to return recommendations only.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    summary = get_review_summary_data(reviews, company)
    return {
        "company": summary.get("company_name"),
        "risk_score": summary.get("risk_score"),
        "risk_level": summary.get("risk_level"),
        "trend": summary.get("ai_observations", {}).get("trend"),
        "ai_recommendations": summary.get("ai_recommendations", []),
    }
