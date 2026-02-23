# FILE: app/services/ai_insights.py
"""
AI Insights service for review analytics.

This module centralizes the logic to compute metrics used by the dashboard:
- Sentiment buckets (Positive / Neutral / Negative)
- Average rating
- Monthly trend signal (improving / stable / declining)
- Risk score & level
- Aspect mining from review text using a lightweight lexicon
- Actionable recommendations mapped from negative keywords
- Day-wise (daily) time series

The functions are pure-Python and accept SQLAlchemy ORM objects or any objects
that expose the attributes used below (id, rating, text, review_date, etc.).
They DO NOT perform database or network I/O; routes should fetch data and then
call into this module.

Usage (from a FastAPI route):

    from app.services.ai_insights import analyze_reviews

    result = analyze_reviews(reviews, company, start_dt, end_dt, include_aspects=True)
    return result

"""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
import re

# ─────────────────────────────────────────────────────────────
# Configuration (tweak thresholds here if needed)
# ─────────────────────────────────────────────────────────────
TREND_DELTA_THRESHOLD = 0.3  # ≥ +0.3 improving, ≤ -0.3 declining
RISK_DECLINING_BONUS = 15    # extra points if trend is declining
DEFAULT_WINDOW_DAYS = 180     # used only when start/end are None
MAX_RECOMMENDATIONS = 6

# ─────────────────────────────────────────────────────────────
# Lightweight NLP helpers (no external dependencies)
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
    """Map star rating → sentiment label.
    4–5 → Positive, 3/None → Neutral, 1–2 → Negative
    """
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
# Data shapes
# ─────────────────────────────────────────────────────────────
@dataclass
class SimpleReview:
    rating: Optional[float]
    text: Optional[str]
    review_date: Optional[datetime]

    @classmethod
    def from_any(cls, obj: Any) -> "SimpleReview":
        # Accept ORM objects or dict-like payloads
        rating = getattr(obj, "rating", None)
        text = getattr(obj, "text", None)
        review_date = getattr(obj, "review_date", None)
        if review_date and not isinstance(review_date, datetime):
            # best effort: ignore non-datetime
            review_date = None
        return cls(rating=rating, text=text, review_date=review_date)


# ─────────────────────────────────────────────────────────────
# Core computations
# ─────────────────────────────────────────────────────────────
def _parse_review_date(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _daily_buckets_range(reviews: List[SimpleReview], start: datetime, end: datetime) -> List[Dict[str, Any]]:
    start_day = start.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end_day = end.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
    days_diff = (end_day.date() - start_day.date()).days + 1
    if days_diff < 1:
        return []

    buckets: Dict[str, Dict[str, Any]] = {}
    for i in range(days_diff):
        d = (start_day + timedelta(days=i)).date().isoformat()
        buckets[d] = {
            "date": d,
            "ratings": [],
            "scores": [],
            "counts": {"Positive": 0, "Neutral": 0, "Negative": 0},
        }

    for r in reviews:
        dt = _parse_review_date(r.review_date)
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
            **b["counts"],
        }
        for d, b in sorted(buckets.items())
    ]

def _compute_trend(month_to_ratings: Dict[str, List[float]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    trend_list = [
        {"month": m, "avg_rating": round(sum(v) / len(v), 2)}
        for m, v in sorted(month_to_ratings.items())
    ]
    trend = {"signal": "insufficient_data", "delta": 0.0}
    if len(trend_list) >= 3:
        last = trend_list[-1]["avg_rating"]
        first = trend_list[0]["avg_rating"]
        delta = round(last - first, 2)
        if len(trend_list) >= 6:
            last3 = sum(x["avg_rating"] for x in trend_list[-3:]) / 3
            prev3 = sum(x["avg_rating"] for x in trend_list[-6:-3]) / 3
            delta = round(last3 - prev3, 2)
        if delta <= -TREND_DELTA_THRESHOLD:
            trend = {"signal": "declining", "delta": delta}
        elif delta >= TREND_DELTA_THRESHOLD:
            trend = {"signal": "improving", "delta": delta}
        else:
            trend = {"signal": "stable", "delta": delta}
    return trend_list, trend

def analyze_reviews(
    reviews: Iterable[Any],
    company: Any,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    include_aspects: bool = True,
) -> Dict[str, Any]:
    """Compute the insight payload for the dashboard.

    Parameters
    ----------
    reviews : Iterable[Any]
        ORM Review objects or dict-like rows with .rating, .text, .review_date
    company : Any
        ORM Company object (used only for name fallback)
    start, end : datetime (optional)
        Inclusive window; defaults to last DEFAULT_WINDOW_DAYS
    include_aspects : bool
        When True (default), returns aspect counts from keyword mapping

    Returns
    -------
    Dict[str, Any]
        JSON-serializable dictionary ready for the dashboard.
    """
    now = datetime.now(timezone.utc)
    start = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS))
    end = end or now
    if end < start:
        start, end = end, start

    # Normalize incoming rows
    simplified: List[SimpleReview] = [SimpleReview.from_any(r) for r in reviews]

    # Filter by window
    windowed: List[SimpleReview] = []
    for r in simplified:
        dt = _parse_review_date(r.review_date)
        if dt and (start <= dt <= end):
            windowed.append(r)

    company_name = getattr(company, "name", None) or f"ID {getattr(company, 'id', '')}".strip()

    if not windowed:
        return {
            "company_name": company_name,
            "total_reviews": 0,
            "avg_rating": 0.0,
            "risk_score": 0,
            "risk_level": "Low",
            "trend_data": [],
            "trend": {"signal": "insufficient_data", "delta": 0.0},
            "sentiments": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "ai_recommendations": [],
            "daily_series": [],
            "aspects": [],
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "payload_version": "3.3",
        }

    sentiments: Dict[str, int] = {"Positive": 0, "Neutral": 0, "Negative": 0}
    month_to_ratings: Dict[str, List[float]] = defaultdict(list)
    neg_keywords: List[str] = []
    aspect_counter: Counter = Counter()

    for r in windowed:
        lbl = classify_sentiment(r.rating)
        sentiments[lbl] += 1
        dt = _parse_review_date(r.review_date)
        if dt:
            month_to_ratings[dt.strftime("%Y-%m")].append(r.rating or 0)
        if r.text:
            toks = extract_keywords(r.text)
            if lbl == "Negative":
                neg_keywords.extend(toks)
            if include_aspects:
                for a in map_aspects(toks):
                    aspect_counter[a] += 1

    # Trend
    trend_list, trend = _compute_trend(month_to_ratings)

    total = len(windowed)
    rated = [r.rating for r in windowed if r.rating is not None]
    avg_rating = round(sum(rated) / len(rated), 2) if rated else 0.0

    # Risk score: share of negatives plus a penalty if trend is declining
    neg_share = sentiments["Negative"] / total if total else 0
    risk_score = round(neg_share * 100 + (RISK_DECLINING_BONUS if trend["signal"] == "declining" else 0), 1)
    risk_level = "High" if risk_score >= 45 else "Medium" if risk_score >= 20 else "Low"

    # Recommendations from most frequent negative keywords
    recs = []
    seen = set()
    for kw, count in Counter(neg_keywords).most_common(MAX_RECOMMENDATIONS):
        if kw in seen:
            continue
        seen.add(kw)
        recs.append({
            "area": kw,
            "count": count,
            "priority": "High" if count >= 5 else "Medium",
            "action": _action_for_keyword(kw),
        })

    # Day-wise series
    daily_series = _daily_buckets_range(windowed, start, end)

    aspects = [{"aspect": k, "count": v} for k, v in aspect_counter.most_common()] if include_aspects else []

    return {
        "company_name": company_name,
        "total_reviews": total,
        "avg_rating": avg_rating,
        "sentiments": sentiments,
        "trend_data": trend_list,
        "trend": trend,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "ai_recommendations": recs,
        "daily_series": daily_series,
        "aspects": aspects,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "payload_version": "3.3",
    }


__all__ = [
    "analyze_reviews",
    "classify_sentiment",
    "extract_keywords",
    "map_aspects",
    "ASPECT_LEXICON",
    "ACTION_MAP",
]
