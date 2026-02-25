# FILE: app/services/ai_insights.py

from typing import List, Dict, Any, Optional
from collections import Counter, defaultdict
from datetime import datetime
import re

from app.models import Review, Company

def _sent_map(cat: Optional[str]) -> int:
    if cat == "Positive": return 1
    if cat == "Negative": return -1
    return 0

def analyze_reviews(
    reviews: List[Review],
    company: Optional[Company],
    sdt: Optional[datetime],
    edt: Optional[datetime],
) -> Dict[str, Any]:
    """
    Lightweight analytics used to populate the Executive Summary and visuals.
    """
    n = len(reviews)
    avg_rating = sum(float(r.rating) for r in reviews if r.rating is not None) / n if n else 0.0
    sent_vals = [_sent_map(r.sentiment_category) for r in reviews]
    avg_sent = sum(sent_vals) / n if n else 0.0

    # Emotion breakdown (by label)
    emotions = Counter([(r.emotion_label or "Neutral") for r in reviews])

    # Aspect performance: if aspect_summary stored, average per aspect.score
    aspect_scores: Dict[str, List[float]] = defaultdict(list)
    for r in reviews:
        if r.aspect_summary:
            for k, v in (r.aspect_summary or {}).items():
                score = (v.get("score") if isinstance(v, dict) else None)
                if isinstance(score, (int, float)):
                    aspect_scores[k].append(float(score))
    aspects = {k: sum(v)/len(v) if v else 0.0 for k, v in aspect_scores.items()}

    # Keywords/topics (simple token freq fallback)
    all_text = " ".join((r.text or "") for r in reviews)
    tokens = [t.lower() for t in re.findall(r"[A-Za-z]{3,}", all_text)]
    top_keywords = [w for w, _ in Counter(tokens).most_common(8)]

    return {
        "avg_rating": avg_rating,
        "emotion_breakdown": dict(emotions),
        "aspect_performance": aspects,
        "executive_summary": {
            "sentiment_score": avg_sent,
            "predictive_signal": "Stable",
            "risk_level": "Low" if avg_sent >= 0 else "Elevated",
            "top_keywords": top_keywords
        },
        "api_status": {"google_api_health": "Unknown", "sync_timestamp": None},
        "payload_version": "7.0-Enterprise"
    }

def hour_heatmap(reviews: List[Review], sdt: Optional[datetime], edt: Optional[datetime]) -> Dict[str, int]:
    """
    Returns a histogram of review volume by hour-of-day: {"00": n, ... "23": n}
    """
    hist = {f"{h:02d}": 0 for h in range(24)}
    for r in reviews:
        if r.review_date:
            hist[f"{r.review_date.hour:02d}"] += 1
    return hist

def detect_anomalies(reviews: List[Review]) -> List[Dict[str, Any]]:
    """
    Naive anomaly: flag days with > 95th percentile volume.
    """
    by_day = defaultdict(int)
    for r in reviews:
        if r.review_date:
            by_day[r.review_date.date().isoformat()] += 1
    volumes = sorted(by_day.values())
    if not volumes:
        return []
    p95_idx = max(int(0.95 * (len(volumes) - 1)), 0)
    thr = volumes[p95_idx]
    alerts = []
    for day, v in by_day.items():
        if v >= thr and v > 0 and len(volumes) > 5:
            alerts.append({"day": day, "volume": v, "severity": "warning", "title": "Volume spike"})
    return alerts

def suggest_reply(text: str, rating: int, sentiment: str, company_name: str) -> str:
    """
    Friendly default reply generator used by /reviews/{id}/reply/suggest
    """
    intro = "Thank you for your feedback!"
    if rating and rating <= 2 or sentiment == "Negative":
        intro = "We’re sorry to hear about the experience."
    body = "We appreciate you taking the time to share this. "
    action = "Please DM us your details so we can assist further." if rating <= 3 else "We hope to see you again soon!"
    return f"{intro} {body}{action} — {company_name}"
