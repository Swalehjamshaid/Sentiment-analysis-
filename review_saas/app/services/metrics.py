# FILE: app/services/metrics.py

from datetime import datetime
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from collections import defaultdict

from app.models import Review

def _fmt_day(dt: Optional[datetime]) -> str:
    return dt.date().isoformat() if dt else ""

def build_chart_payloads(db: Session, company_id: int, sdt: Optional[datetime] = None, edt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Produces:
      labels: [day...]
      sentiment: [avg_sentiment per day]  (fallback computes +1/0/-1 mean)
      rating: [avg_rating per day]
      dist: {"1":n1,...,"5":n5}
      correlation: [{"sentiment": x, "rating": y}, ...]
      benchmark: {"labels":[...], "series":[{"name":"You","values":[...]}]}
    """
    q = db.query(Review).filter(Review.company_id == company_id)
    if sdt: q = q.filter(Review.review_date >= sdt)
    if edt: q = q.filter(Review.review_date <= edt)

    rows = q.all()
    # Group by day
    by_day: Dict[str, List[Review]] = defaultdict(list)
    dist = {str(i): 0 for i in range(1, 6)}
    corr = []

    for r in rows:
        day = _fmt_day(r.review_date)
        by_day[day].append(r)
        if r.rating in (1, 2, 3, 4, 5):
            dist[str(int(r.rating))] += 1
        # sentiment to numeric: Positive=1, Neutral=0, Negative=-1
        s_val = 0
        if r.sentiment_category == "Positive": s_val = 1
        elif r.sentiment_category == "Negative": s_val = -1
        if r.rating is not None:
            corr.append({"sentiment": s_val, "rating": float(r.rating)})

    labels = sorted(by_day.keys())
    sentiment_series = []
    rating_series = []
    for d in labels:
        bucket = by_day[d]
        if not bucket:
            sentiment_series.append(0.0)
            rating_series.append(0.0)
            continue
        # Average sentiment (mapped numeric)
        s_vals = []
        r_vals = []
        for r in bucket:
            s = 0
            if r.sentiment_category == "Positive": s = 1
            elif r.sentiment_category == "Negative": s = -1
            s_vals.append(s)
            if r.rating is not None:
                r_vals.append(float(r.rating))
        sentiment_series.append(sum(s_vals) / len(s_vals) if s_vals else 0.0)
        rating_series.append(sum(r_vals) / len(r_vals) if r_vals else 0.0)

    # Minimal benchmark: only self (placeholders for competitors can be added later)
    benchmark = {
        "labels": labels,
        "series": [
            {"name": "You", "values": rating_series},
        ]
    }

    return {
        "labels": labels,
        "sentiment": sentiment_series,
        "rating": rating_series,
        "dist": dist,
        "correlation": corr,
        "benchmark": benchmark,
    }

def build_kpis(db: Session, company_id: int, sdt: Optional[datetime] = None, edt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Returns kpi dict with keys used in the template:
      avg_rating, avg_sentiment, pos, neu, neg, review_count, review_growth, avg_response_time, response_rate
    """
    q = db.query(Review).filter(Review.company_id == company_id)
    if sdt: q = q.filter(Review.review_date >= sdt)
    if edt: q = q.filter(Review.review_date <= edt)
    rows = q.all()

    n = len(rows)
    pos = sum(1 for r in rows if r.sentiment_category == "Positive")
    neu = sum(1 for r in rows if r.sentiment_category == "Neutral")
    neg = sum(1 for r in rows if r.sentiment_category == "Negative")

    avg_rating = (sum(float(r.rating) for r in rows if r.rating is not None) / n) if n else None
    # Map Positive=1, Neutral=0, Negative=-1
    sentiments = []
    for r in rows:
        if r.sentiment_category == "Positive": sentiments.append(1)
        elif r.sentiment_category == "Negative": sentiments.append(-1)
        else: sentiments.append(0)
    avg_sentiment = (sum(sentiments) / n) if n else None

    # Simple growth placeholder: compare first half vs second half volumes
    growth = "—"
    if n >= 2:
        first = rows[: n // 2]
        second = rows[n // 2 :]
        if first:
            delta = (len(second) - len(first)) / len(first) * 100
            growth = f"{delta:.1f}%"

    return {
        "avg_rating": f"{avg_rating:.2f}" if avg_rating is not None else "—",
        "avg_sentiment": f"{avg_sentiment:.2f}" if avg_sentiment is not None else "—",
        "pos": pos, "neu": neu, "neg": neg,
        "review_count": n,
        "review_growth": growth,
        "avg_response_time": "—",  # populate if you track Reply timestamps vs Review time
        "response_rate": "—",      # requires a responded flag/Reply join
    }
