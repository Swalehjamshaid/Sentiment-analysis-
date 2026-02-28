# FILE: app/services/ai_insights.py
"""
AI Insights service for review analytics (dashboard-ready).
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
    """Legacy rating→sentiment mapping."""
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
        """Adapter that handles both ORM objects and dictionaries."""
        rating = getattr(obj, "rating", None)
        text = getattr(obj, "text", None)
        review_date = getattr(obj, "review_date", None)
        reviewer_name = getattr(obj, "reviewer_name", None)
        reviewer_avatar = getattr(obj, "reviewer_avatar", None)
        external_id = getattr(obj, "external_id", None)
        language = getattr(obj, "language", None)
        sentiment_category = getattr(obj, "sentiment_category", None)
        keywords = getattr(obj, "keywords", None)

        source = getattr(obj, "source", None)
        if not source and isinstance(external_id, str) and external_id.startswith("gplace:"):
            source = "google"

        # Force UTC normalization
        if review_date and isinstance(review_date, datetime):
            if review_date.tzinfo is None:
                review_date = review_date.replace(tzinfo=timezone.utc)
            else:
                review_date = review_date.astimezone(timezone.utc)

        return cls(
            rating=rating, text=text, review_date=review_date,
            source=source, sentiment_category=sentiment_category,
            keywords=keywords, reviewer_name=reviewer_name,
            reviewer_avatar=reviewer_avatar, external_id=external_id,
            language=language, author=getattr(obj, "author", None) or reviewer_name
        )

# ─────────────────────────────────────────────────────────────
# Core computations
# ─────────────────────────────────────────────────────────────
def _parse_review_date(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _review_sentiment(sr: SimpleReview) -> str:
    """Prefer explicit sentiment_category; fallback to rating-based classification."""
    cat = (sr.sentiment_category or "").strip().lower()
    if cat:
        if cat.startswith("pos"): return "Positive"
        if cat.startswith("neg"): return "Negative"
        return "Neutral"
    return classify_sentiment(sr.rating)

def _daily_buckets_range(reviews: List[SimpleReview], start: datetime, end: datetime) -> List[Dict[str, Any]]:
    start_day = start.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end_day = end.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
    days_diff = (end_day.date() - start_day.date()).days + 1
    if days_diff < 1: return []

    buckets = { (start_day + timedelta(days=i)).date().isoformat(): {
        "date": (start_day + timedelta(days=i)).date().isoformat(),
        "ratings": [], "scores": [], "counts": {"Positive": 0, "Neutral": 0, "Negative": 0}
    } for i in range(days_diff) }

    for r in reviews:
        dt = _parse_review_date(r.review_date)
        if not dt or not (start_day <= dt <= end_day): continue
        day_str = dt.date().isoformat()
        lbl = _review_sentiment(r)
        score = 1.0 if lbl == "Positive" else -1.0 if lbl == "Negative" else 0.0
        buckets[day_str]["ratings"].append(r.rating or 0.0)
        buckets[day_str]["scores"].append(score)
        buckets[day_str]["counts"][lbl] += 1

    return [ {
        "date": d,
        "avg_rating": round(sum(b["ratings"]) / len(b["ratings"]), 2) if b["ratings"] else None,
        "sent_score": round(sum(b["scores"]) / len(b["scores"]), 3) if b["scores"] else 0.0,
        **b["counts"]
    } for d, b in sorted(buckets.items()) ]

def _compute_trend(month_to_ratings: Dict[str, List[float]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    trend_list = [ {"month": m, "avg_rating": round(sum(v) / len(v), 2)} for m, v in sorted(month_to_ratings.items()) ]
    trend = {"signal": "insufficient_data", "delta": 0.0}
    if len(trend_list) >= 3:
        last = trend_list[-1]["avg_rating"]
        first = trend_list[0]["avg_rating"]
        delta = round(last - first, 2)
        if len(trend_list) >= 6:
            last3 = sum(x["avg_rating"] for x in trend_list[-3:]) / 3
            prev3 = sum(x["avg_rating"] for x in trend_list[-6:-3]) / 3
            delta = round(last3 - prev3, 2)
        
        if delta <= -TREND_DELTA_THRESHOLD: trend = {"signal": "declining", "delta": delta}
        elif delta >= TREND_DELTA_THRESHOLD: trend = {"signal": "improving", "delta": delta}
        else: trend = {"signal": "stable", "delta": delta}
    return trend_list, trend

def analyze_reviews(reviews: Iterable[Any], company: Any, start: Optional[datetime] = None, end: Optional[datetime] = None, include_aspects: bool = True) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    start, end = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS)), end or now
    if end < start: start, end = end, start

    simplified = [SimpleReview.from_any(r) for r in reviews]
    windowed = [r for r in simplified if (dt := _parse_review_date(r.review_date)) and start <= dt <= end]
    company_name = getattr(company, "name", None) or f"ID {getattr(company, 'id', '')}".strip()

    if not windowed:
        return {
            "company_name": company_name, "total_reviews": 0, "avg_rating": 0.0, "risk_score": 0, "risk_level": "Low",
            "trend_data": [], "trend": {"signal": "insufficient_data", "delta": 0.0},
            "sentiments": {"Positive": 0, "Neutral": 0, "Negative": 0}, "ai_recommendations": [],
            "daily_series": [], "aspects": [], "window": {"start": start.isoformat(), "end": end.isoformat()}, "payload_version": "3.5"
        }

    sentiments = {"Positive": 0, "Neutral": 0, "Negative": 0}
    month_to_ratings = defaultdict(list)
    neg_keywords, aspect_counter = [], Counter()

    for r in windowed:
        lbl = _review_sentiment(r)
        sentiments[lbl] += 1
        dt = _parse_review_date(r.review_date)
        if dt: month_to_ratings[dt.strftime("%Y-%m")].append(r.rating or 0.0)
        if r.text:
            toks = extract_keywords(r.text)
            if lbl == "Negative": neg_keywords.extend(toks)
            if include_aspects:
                for a in map_aspects(toks): aspect_counter[a] += 1

    trend_list, trend = _compute_trend(month_to_ratings)
    rated = [r.rating for r in windowed if r.rating is not None]
    avg_rating = round(sum(rated) / len(rated), 2) if rated else 0.0

    neg_share = sentiments["Negative"] / len(windowed)
    risk_score = round(neg_share * 100 + (RISK_DECLINING_BONUS if trend["signal"] == "declining" else 0), 1)
    risk_level = "High" if risk_score >= 45 else "Medium" if risk_score >= 20 else "Low"

    recs, seen = [], set()
    for kw, count in Counter(neg_keywords).most_common(MAX_RECOMMENDATIONS):
        if kw not in seen:
            seen.add(kw)
            recs.append({"area": kw, "count": count, "priority": "High" if count >= 5 else "Medium", "action": _action_for_keyword(kw)})

    return {
        "company_name": company_name, "total_reviews": len(windowed), "avg_rating": avg_rating,
        "sentiments": sentiments, "trend_data": trend_list, "trend": trend, "risk_score": risk_score, "risk_level": risk_level,
        "ai_recommendations": recs, "daily_series": _daily_buckets_range(windowed, start, end),
        "aspects": [{"aspect": k, "count": v} for k, v in aspect_counter.most_common()] if include_aspects else [],
        "window": {"start": start.isoformat(), "end": end.isoformat()}, "payload_version": "3.5"
    }

# ─────────────────────────────────────────────────────────────
# Dashboard Helpers
# ─────────────────────────────────────────────────────────────

def metrics_payload(reviews: Iterable[Any], start: Optional[datetime] = None, end: Optional[datetime] = None) -> Dict[str, Any]:
    p = analyze_reviews(reviews, company=type("C", (), {"id": ""})(), start=start, end=end, include_aspects=False)
    return {"total": p["total_reviews"], "avg_rating": float(p["avg_rating"]), "risk_score": float(p["risk_score"]), "risk_level": p["risk_level"]}

def trend_timeseries(reviews: Iterable[Any], start: Optional[datetime] = None, end: Optional[datetime] = None) -> Dict[str, List[Any]]:
    now = datetime.now(timezone.utc)
    start, end = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS)), end or now
    series = _daily_buckets_range([SimpleReview.from_any(r) for r in reviews], start, end)
    return {"labels": [row["date"] for row in series], "data": [float(row["avg_rating"] or 0.0) for row in series]}

def sentiment_buckets(reviews: Iterable[Any], start: Optional[datetime] = None, end: Optional[datetime] = None) -> Dict[str, int]:
    now = datetime.now(timezone.utc)
    start, end = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS)), end or now
    pos = neu = neg = 0
    for r in (SimpleReview.from_any(x) for x in reviews):
        dt = _parse_review_date(r.review_date)
        if not dt or not (start <= dt <= end): continue
        lbl = _review_sentiment(r)
        if lbl == "Positive": pos += 1
        elif lbl == "Negative": neg += 1
        else: neu += 1
    return {"pos": pos, "neu": neu, "neg": neg}

def sources_breakdown(reviews: Iterable[Any], start: Optional[datetime] = None, end: Optional[datetime] = None) -> Dict[str, List[Any]]:
    now = datetime.now(timezone.utc)
    start, end = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS)), end or now
    buckets = defaultdict(int)
    for r in (SimpleReview.from_any(x) for x in reviews):
        dt = _parse_review_date(r.review_date)
        if not dt or not (start <= dt <= end): continue
        buckets[(r.source or "unknown").strip() or "unknown"] += 1
    return {"labels": list(buckets.keys()), "data": list(buckets.values())}

def hour_heatmap(reviews: Iterable[Any], start: Optional[datetime] = None, end: Optional[datetime] = None) -> Dict[str, List[int]]:
    now = datetime.now(timezone.utc)
    start, end = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS)), end or now
    hours = [0] * 24
    for r in (SimpleReview.from_any(x) for x in reviews):
        dt = _parse_review_date(r.review_date)
        if dt and (start <= dt <= end): hours[dt.hour] += 1
    return {"labels": list(range(24)), "data": hours}

def top_keywords(reviews: Iterable[Any], start: Optional[datetime] = None, end: Optional[datetime] = None, top_n: int = 20) -> Dict[str, List[Any]]:
    now = datetime.now(timezone.utc)
    start, end = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS)), end or now
    buckets = defaultdict(int)
    for r in (SimpleReview.from_any(x) for x in reviews):
        dt = _parse_review_date(r.review_date)
        if not dt or not (start <= dt <= end): continue
        if r.keywords:
            for p in [p.strip().lower() for p in str(r.keywords).replace(";", ",").split(",") if p.strip()]: buckets[p] += 1
        else:
            for tok in extract_keywords(r.text or ""): buckets[tok] += 1
    items = sorted(buckets.items(), key=lambda x: x[1], reverse=True)[:max(1, min(100, top_n))]
    return {"labels": [k for k, _ in items], "data": [int(v) for _, v in items]}

def detect_alerts(reviews: Iterable[Any], start: Optional[datetime] = None, end: Optional[datetime] = None, window_days: int = 14) -> Dict[str, List[Dict[str, Any]]]:
    simplified = sorted((SimpleReview.from_any(x) for x in reviews), key=lambda r: _parse_review_date(r.review_date) or datetime.min.replace(tzinfo=timezone.utc))
    dts = [d for d in (_parse_review_date(r.review_date) for r in simplified) if d]
    if not dts: return {"alerts": []}
    start, end = start or min(dts), end or max(dts)
    r_start = end - timedelta(days=window_days)
    p_start, p_end = r_start - timedelta(days=window_days), r_start

    def _avg(rs):
        v = [float(r.rating) for r in rs if r.rating is not None]
        return sum(v)/len(v) if v else 0.0

    recent = [r for r in simplified if (dt := _parse_review_date(r.review_date)) and r_start <= dt <= end]
    prev = [r for r in simplified if (dt := _parse_review_date(r.review_date)) and p_start <= dt < p_end]
    r_avg, p_avg, r_cnt, p_cnt = _avg(recent), _avg(prev), len(recent), len(prev)

    alerts, delta = [], r_avg - p_avg
    if delta <= -0.5 and r_cnt >= 10: alerts.append({"type": "warning", "title": "Rating drop", "message": f"Rating fell by {abs(round(delta, 2))}."})
    if delta >= 0.5 and r_cnt >= 10: alerts.append({"type": "success", "title": "Improvement", "message": f"Rating rose by {round(delta, 2)}."})
    if p_cnt and r_cnt >= p_cnt * 2 and r_cnt >= 20: alerts.append({"type": "info", "title": "Volume spike", "message": "Volume doubled."})
    return {"alerts": alerts}

def revenue_proxy_monthly(reviews: Iterable[Any], start: Optional[datetime] = None, end: Optional[datetime] = None, months_back: int = 6) -> Dict[str, List[Any]]:
    now = datetime.now(timezone.utc)
    start, end = start or (now - timedelta(days=DEFAULT_WINDOW_DAYS)), end or now
    monthly = defaultdict(lambda: {"count": 0, "sum_rating": 0.0})
    for r in (SimpleReview.from_any(x) for x in reviews):
        dt = _parse_review_date(r.review_date)
        if dt and (start <= dt <= end):
            key = dt.strftime("%Y-%m")
            monthly[key]["count"] += 1
            monthly[key]["sum_rating"] += float(r.rating or 0.0)

    keys = sorted(monthly.keys())[-months_back:]
    labels, data = [], []
    for k in keys:
        labels.append(datetime.strptime(k, "%Y-%m").strftime("%b %Y"))
        cnt = monthly[k]["count"]
        avg = monthly[k]["sum_rating"] / cnt if cnt else 0.0
        data.append(round(max(0.0, cnt * (avg / 5.0) * 100.0), 2))
    return {"labels": labels or ["Jan", "Feb", "Mar", "Apr", "May", "Jun"], "data": data or [0]*6}

__all__ = ["analyze_reviews", "classify_sentiment", "extract_keywords", "map_aspects", "ASPECT_LEXICON", "ACTION_MAP",
           "metrics_payload", "trend_timeseries", "sentiment_buckets", "sources_breakdown", "hour_heatmap", "top_keywords", "detect_alerts", "revenue_proxy_monthly"]
