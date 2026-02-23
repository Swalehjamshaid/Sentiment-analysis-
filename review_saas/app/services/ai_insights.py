# FILE: app/services/ai_insights.py
"""
AI Insights service for review analytics (dashboard-ready).

• Computes: sentiment buckets, averages, trend signal, risk score & level,
  aspect counts, recommendations, daily time series.
• Pure-Python: no DB/network access; routes must supply ORM rows.
• Aligns with models in app/models.py (Review + Company).

This version:
- Prefers Review.sentiment_category (fallback to rating) for sentiment.
- Infers source="google" for external_id like 'gplace:...'.
- Normalizes datetimes to UTC.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
import re

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────
TREND_DELTA_THRESHOLD = 0.3  # ≥ +0.3 improving, ≤ -0.3 declining
RISK_DECLINING_BONUS = 15    # extra points if trend is declining
DEFAULT_WINDOW_DAYS = 180    # used only when start/end are None
MAX_RECOMMENDATIONS = 6

# ─────────────────────────────────────────────────────────────
# Lightweight NLP helpers
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
    """Legacy rating→sentiment mapping.
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
    # Optional / dashboard-friendly extras
    source: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    url: Optional[str] = None
    sentiment_category: Optional[str] = None
    keywords: Optional[str] = None
    reviewer_name: Optional[str] = None
    reviewer_avatar: Optional[str] = None
    external_id: Optional[str] = None
    language: Optional[str] = None

    @classmethod
    def from_any(cls, obj: Any) -> "SimpleReview":
        """Tolerant adapter: pulls known attributes from ORM/dict-like rows."""
        rating = getattr(obj, "rating", None)
        text = getattr(obj, "text", None)
        review_date = getattr(obj, "review_date", None)

        # Align with your Review model (reviewer_name, reviewer_avatar, external_id, language)
        reviewer_name = getattr(obj, "reviewer_name", None)
        reviewer_avatar = getattr(obj, "reviewer_avatar", None)
        external_id = getattr(obj, "external_id", None)
        language = getattr(obj, "language", None)

        # Generic fields some dashboards use
        title = getattr(obj, "title", None)
        url = getattr(obj, "url", None)
        # `author` fallback to reviewer_name
        author = getattr(obj, "author", None) or reviewer_name
        sentiment_category = getattr(obj, "sentiment_category", None)
        keywords = getattr(obj, "keywords", None)

        # Optional source: if not present, infer from external_id prefix
        source = getattr(obj, "source", None)
        if not source and isinstance(external_id, str) and external_id.startswith("gplace:"):
            source = "google"

        # Normalize datetime
        if review_date and not isinstance(review_date, datetime):
            review_date = None

        return cls(
            rating=rating,
            text=text,
            review_date=review_date,
            source=source,
            title=title,
            author=author,
            url=url,
            sentiment_category=sentiment_category,
            keywords=keywords,
            reviewer_name=reviewer_name,
            reviewer_avatar=reviewer_avatar,
            external_id=external_id,
            language=language,
        )

# ─────────────────────────────────────────────────────────────
# Core computations
# ─────────────────────────────────────────────────────────────
def _parse_review_date(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _review_sentiment(sr: SimpleReview) -> str:
    """Prefer explicit sentiment_category; fallback to rating."""
    cat = (sr.sentiment_category or "").strip().lower()
    if cat:
        if cat.startswith("pos"):
            return "Positive"
        if cat.startswith("neg"):
            return "Negative"
        return "Neutral"
    return classify_sentiment(sr.rating)

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
        lbl = _review_sentiment(r)
        score = 1.0 if lbl == "Positive" else -1.0 if lbl == "Negative" else 0.0
        buckets[day_str]["ratings"].append(r.rating or 0.0)
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
    """Compute the insight payload for the dashboard."""

    now = datetime.now(timezone.utc)
    start = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS))
    end = end or now
    if end < start:
        start, end = end, start

    simplified: List[SimpleReview] = [SimpleReview.from_any(r) for r in reviews]

    # Filter window
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
            "payload_version": "3.4",
        }

    sentiments: Dict[str, int] = {"Positive": 0, "Neutral": 0, "Negative": 0}
    month_to_ratings: Dict[str, List[float]] = defaultdict(list)
    neg_keywords: List[str] = []
    aspect_counter: Counter = Counter()

    for r in windowed:
        lbl = _review_sentiment(r)
        sentiments[lbl] += 1
        dt = _parse_review_date(r.review_date)
        if dt:
            month_to_ratings[dt.strftime("%Y-%m")].append(r.rating or 0.0)
        if r.text:
            toks = extract_keywords(r.text)
            if lbl == "Negative":
                neg_keywords.extend(toks)
            if include_aspects:
                for a in map_aspects(toks):
                    aspect_counter[a] += 1

    trend_list, trend = _compute_trend(month_to_ratings)

    total = len(windowed)
    rated = [r.rating for r in windowed if r.rating is not None]
    avg_rating = round(sum(rated) / len(rated), 2) if rated else 0.0

    # Risk score: share of negatives plus a penalty if trend is declining
    neg_share = sentiments["Negative"] / total if total else 0.0
    risk_score = round(neg_share * 100 + (RISK_DECLINING_BONUS if trend["signal"] == "declining" else 0), 1)
    risk_level = "High" if risk_score >= 45 else "Medium" if risk_score >= 20 else "Low"

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
        "payload_version": "3.4",
    }

# ─────────────────────────────────────────────────────────────
# Dashboard-oriented helpers
# ─────────────────────────────────────────────────────────────
def metrics_payload(
    reviews: Iterable[Any],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict[str, Any]:
    payload = analyze_reviews(reviews, company=type("C", (), {"name": ""})(), start=start, end=end, include_aspects=False)
    return {
        "total": payload.get("total_reviews", 0),
        "avg_rating": float(payload.get("avg_rating", 0.0)),
        "risk_score": float(payload.get("risk_score", 0.0)),
        "risk_level": payload.get("risk_level", "Low"),
    }

def trend_timeseries(
    reviews: Iterable[Any],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict[str, List[Any]]:
    now = datetime.now(timezone.utc)
    start = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS))
    end = end or now
    simplified = [SimpleReview.from_any(r) for r in reviews]
    series = _daily_buckets_range(simplified, start, end)
    labels = [row["date"] for row in series]
    data = [float(row["avg_rating"] or 0.0) for row in series]
    return {"labels": labels, "data": data}

def sentiment_buckets(
    reviews: Iterable[Any],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict[str, int]:
    now = datetime.now(timezone.utc)
    start = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS))
    end = end or now
    simplified = [SimpleReview.from_any(r) for r in reviews]
    pos = neu = neg = 0
    for r in simplified:
        dt = _parse_review_date(r.review_date)
        if not dt or not (start <= dt <= end):
            continue
        lbl = _review_sentiment(r)
        if lbl == "Positive":
            pos += 1
        elif lbl == "Negative":
            neg += 1
        else:
            neu += 1
    return {"pos": int(pos), "neu": int(neu), "neg": int(neg)}

def sources_breakdown(
    reviews: Iterable[Any],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict[str, List[Any]]:
    now = datetime.now(timezone.utc)
    start = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS))
    end = end or now
    buckets: Dict[str, int] = defaultdict(int)
    for r in (SimpleReview.from_any(x) for x in reviews):
        dt = _parse_review_date(r.review_date)
        if not dt or not (start <= dt <= end):
            continue
        key = (r.source or "unknown").strip() or "unknown"
        buckets[key] += 1
    labels = list(buckets.keys())
    data = [int(buckets[k]) for k in labels]
    return {"labels": labels, "data": data}

def hour_heatmap(
    reviews: Iterable[Any],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict[str, List[int]]:
    now = datetime.now(timezone.utc)
    start = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS))
    end = end or now
    hours = [0] * 24
    for r in (SimpleReview.from_any(x) for x in reviews):
        dt = _parse_review_date(r.review_date)
        if not dt or not (start <= dt <= end):
            continue
        hours[dt.hour] += 1
    return {"labels": list(range(24)), "data": hours}

def top_keywords(
    reviews: Iterable[Any],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    top_n: int = 20,
) -> Dict[str, List[Any]]:
    now = datetime.now(timezone.utc)
    start = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS))
    end = end or now
    buckets: Dict[str, int] = defaultdict(int)

    for r in (SimpleReview.from_any(x) for x in reviews):
        dt = _parse_review_date(r.review_date)
        if not dt or not (start <= dt <= end):
            continue
        if r.keywords:
            parts = [p.strip().lower() for p in str(r.keywords).replace(";", ",").split(",") if p.strip()]
            for p in parts:
                buckets[p] += 1
        else:
            for tok in extract_keywords(r.text or ""):
                buckets[tok] += 1

    items = sorted(buckets.items(), key=lambda x: x[1], reverse=True)[:max(1, min(100, top_n))]
    return {"labels": [k for k, _ in items], "data": [int(v) for _, v in items]}

def detect_alerts(
    reviews: Iterable[Any],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    window_days: int = 14,
) -> Dict[str, List[Dict[str, Any]]]:
    now = datetime.now(timezone.utc)
    simplified = sorted(
        (SimpleReview.from_any(x) for x in reviews),
        key=lambda r: _parse_review_date(r.review_date) or datetime.min.replace(tzinfo=timezone.utc),
    )
    dts = [d for d in (_parse_review_date(r.review_date) for r in simplified) if d]
    if not dts:
        return {"alerts": []}

    min_dt, max_dt = (min(dts), max(dts))
    start = start or min_dt
    end = end or max_dt

    recent_start = end - timedelta(days=window_days)
    prev_start = recent_start - timedelta(days=window_days)
    prev_end = recent_start

    def _avg(rs: List[SimpleReview]) -> float:
        vals = [float(r.rating) for r in rs if r.rating is not None]
        return float(sum(vals) / len(vals)) if vals else 0.0

    recent = [r for r in simplified if (dt := _parse_review_date(r.review_date)) and recent_start <= dt <= end]
    prev = [r for r in simplified if (dt := _parse_review_date(r.review_date)) and prev_start <= dt < prev_end]

    recent_avg = _avg(recent)
    prev_avg = _avg(prev)
    recent_cnt = len(recent)
    prev_cnt = len(prev)

    alerts: List[Dict[str, Any]] = []
    delta = recent_avg - prev_avg

    if delta <= -0.5 and recent_cnt >= 10:
        alerts.append({
            "type": "warning",
            "title": "Rating drop detected",
            "message": f"Average rating fell by {abs(round(delta, 2))} in last {window_days} days.",
            "recent_avg": round(recent_avg, 2),
            "previous_avg": round(prev_avg, 2),
            "recent_count": recent_cnt,
            "previous_count": prev_cnt,
        })
    if delta >= 0.5 and recent_cnt >= 10:
        alerts.append({
            "type": "success",
            "title": "Rating improvement",
            "message": f"Average rating increased by {round(delta, 2)} in last {window_days} days.",
            "recent_avg": round(recent_avg, 2),
            "previous_avg": round(prev_avg, 2),
            "recent_count": recent_cnt,
            "previous_count": prev_cnt,
        })
    if prev_cnt and recent_cnt >= prev_cnt * 2 and recent_cnt >= 20:
        alerts.append({
            "type": "info",
            "title": "Volume spike",
            "message": f"Review volume doubled ({recent_cnt} vs {prev_cnt}).",
            "recent_count": recent_cnt,
            "previous_count": prev_cnt,
        })

    return {"alerts": alerts}

def revenue_proxy_monthly(
    reviews: Iterable[Any],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    months_back: int = 6,
) -> Dict[str, List[Any]]:
    now = datetime.now(timezone.utc)
    start = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS))
    end = end or now

    monthly: Dict[str, Dict[str, float]] = defaultdict(lambda: {"count": 0, "sum_rating": 0.0})
    for r in (SimpleReview.from_any(x) for x in reviews):
        dt = _parse_review_date(r.review_date)
        if not dt or not (start <= dt <= end):
            continue
        key = dt.strftime("%Y-%m")
        monthly[key]["count"] += 1
        monthly[key]["sum_rating"] += float(r.rating or 0.0)

    keys = sorted(monthly.keys())[-months_back:]
    labels: List[str] = []
    data: List[float] = []
    for key in keys:
        ym = datetime.strptime(key, "%Y-%m")
        labels.append(ym.strftime("%b %Y"))
        cnt = monthly[key]["count"]
        avg = (monthly[key]["sum_rating"] / cnt) if cnt else 0.0
        proxy = max(0.0, cnt * (avg / 5.0) * 100.0)
        data.append(round(proxy, 2))

    if not labels:
        labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
        data = [0, 0, 0, 0, 0, 0]

    return {"labels": labels, "data": data}

__all__ = [
    # existing exports
    "analyze_reviews",
    "classify_sentiment",
    "extract_keywords",
    "map_aspects",
    "ASPECT_LEXICON",
    "ACTION_MAP",
    # new dashboard helpers
    "metrics_payload",
    "trend_timeseries",
    "sentiment_buckets",
    "sources_breakdown",
    "hour_heatmap",
    "top_keywords",
    "detect_alerts",
    "revenue_proxy_monthly",
]
