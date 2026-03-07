from __future__ import annotations
import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import Date, and_, case, cast, desc, func, select
from starlette.templating import Jinja2Templates
from app.core.db import get_session
from app.core.models import Company, Review
from app.routes.companies import _require_user

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.dashboard")

# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_DAYS = 30
NEW_REVIEW_DAYS = 7
_STOPWORDS = {
    "the", "and", "to", "a", "an", "in", "is", "it", "of", "for", "on", "was", "with", "at",
    "this", "that", "by", "be", "from", "as", "are", "were", "or", "we", "you", "they", "our",
    "your", "their", "but", "not", "so", "if", "too", "very", "can", "could", "would", "will",
    "has", "have", "had", "do", "did", "does", "just", "also", "than", "then", "there", "here"
}
_POSITIVE_HINTS = {
    "great", "excellent", "good", "friendly", "clean", "amazing", "love", "nice", "comfortable",
    "helpful", "fast", "quick", "tasty", "spacious", "professional", "responsive", "polite",
    "courteous", "beautiful", "quiet", "safe"
}
_NEGATIVE_HINTS = {
    "bad", "poor", "worst", "slow", "dirty", "rude", "problem", "issue", "disappointed",
    "expensive", "noisy", "crowded", "delay", "broken", "smelly", "cold", "hot", "late",
    "unprofessional", "unhelpful"
}
_URGENT_TERMS = {
    "refund", "fraud", "scam", "unsafe", "health", "hygiene", "lawsuit", "legal", "threat",
    "hazard", "poison", "sick", "food poisoning", "expired", "broken glass", "fire", "electrical"
}

def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None

def _range_or_default(start: Optional[str], end: Optional[str], default_days: int = DEFAULT_DAYS) -> Tuple[date, date]:
    """Return (start_date, end_date) using provided YYYY-MM-DD or default last N days inclusive."""
    today = date.today()
    end_dt = _parse_date(end) or today
    start_dt = _parse_date(start) or (end_dt - timedelta(days=default_days - 1))
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    return start_dt, end_dt

def _date_col() -> any:
    """
    Use google_review_time; if model also has created_at, fallback with COALESCE so we don't drop rows
    that lack google_review_time.
    """
    base = getattr(Review, "google_review_time", None)
    created = getattr(Review, "created_at", None)
    if base is not None and created is not None:
        return cast(func.coalesce(Review.google_review_time, Review.created_at), Date)
    # fallback to google_review_time only
    return cast(Review.google_review_time, Date)

def _rating_sent_fallback():
    """Map star ratings to a sentiment proxy for rows missing sentiment_score."""
    return case(
        (Review.rating == 5, 0.8),
        (Review.rating == 4, 0.4),
        (Review.rating == 3, 0.0),
        (Review.rating == 2, -0.4),
        (Review.rating == 1, -0.8),
        else_=0.0,
    )

def _sentiment_label(score: Optional[float]) -> str:
    if score is None:
        return "neutral"
    if score >= 0.35:
        return "positive"
    if score <= -0.25:
        return "negative"
    return "neutral"

def _clean_tokens(text: str) -> List[str]:
    cleaned = re.sub(r"[^a-zA-Z\s]", " ", text.lower())
    return [t for t in cleaned.split() if len(t) > 2 and t not in _STOPWORDS]

def _bigrams(tokens: List[str]) -> List[str]:
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]

def _count_in_period(items: List[str], start_dt: date, end_dt: date, timestamps: List[Optional[datetime]]) -> Counter:
    c = Counter()
    for t, ts in zip(items, timestamps):
        if ts is None:
            continue
        d = ts.date()
        if start_dt <= d <= end_dt:
            c[t] += 1
    return c

# ──────────────────────────────────────────────────────────────────────────────
# Dashboard Page
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Render authenticated dashboard page."""
    uid = _require_user(request)
    if not uid:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Session expired."})
    
    # FIXED: Corrected template name from "dashbord.html" → "dashboard.html"
    # This matches the actual file name and fixes TemplateNotFound error
    return templates.TemplateResponse("dashboard.html", {"request": request})

# ──────────────────────────────────────────────────────────────────────────────
# KPIs & Ratings
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/kpis")
async def api_kpis(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """
    High-level KPIs:
      - total_reviews (in window)
      - avg_rating
      - avg_sentiment (uses sentiment_score; falls back to rating-derived proxy if NULL)
      - new_reviews (last 7 days ending at end_dt)
    """
    start_dt, end_dt = _range_or_default(start, end)
    async with get_session() as session:
        date_col = _date_col()
        avg_sent_expr = func.avg(func.coalesce(Review.sentiment_score, _rating_sent_fallback()))
        stmt = (
            select(
                func.count(Review.id),
                func.avg(Review.rating),
                avg_sent_expr,
            )
            .where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
        )
        total, avg_rating, avg_sent = (await session.execute(stmt)).first() or (0, None, None)
        # New reviews: last NEW_REVIEW_DAYS up to end_dt
        new_start = end_dt - timedelta(days=NEW_REVIEW_DAYS - 1)
        q_new = await session.execute(
            select(func.count(Review.id)).where(and_(Review.company_id == company_id, date_col >= new_start, date_col <= end_dt))
        )
        new_reviews = int(q_new.scalar() or 0)
        return {
            "window": {"start": str(start_dt), "end": str(end_dt)},
            "total_reviews": int(total or 0),
            "avg_rating": round(float(avg_rating or 0.0), 2),
            "avg_sentiment": round(float(avg_sent or 0.0), 3),
            "new_reviews": new_reviews,
        }

@router.get("/api/ratings/distribution")
async def api_ratings_distribution(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Histogram of rating 1..5 within window."""
    start_dt, end_dt = _range_or_default(start, end)
    async with get_session() as session:
        date_col = _date_col()
        stmt = (
            select(Review.rating, func.count(Review.id))
            .where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
            .group_by(Review.rating)
        )
        res = await session.execute(stmt)
        dist = {i: 0 for i in range(1, 6)}
        for rating, cnt in res.all():
            if rating in dist:
                dist[int(rating)] = int(cnt or 0)
        return {"distribution": dist, "window": {"start": str(start_dt), "end": str(end_dt)}}

# ──────────────────────────────────────────────────────────────────────────────
# Trends (Volume, Rating, Sentiment)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/series/reviews")
async def api_series_reviews(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Daily review volume."""
    start_dt, end_dt = _range_or_default(start, end)
    async with get_session() as session:
        date_col = _date_col()
        stmt = (
            select(date_col.label("date"), func.count(Review.id).label("value"))
            .where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
            .group_by("date")
            .order_by("date")
        )
        res = await session.execute(stmt)
        series = [{"date": str(r.date), "value": int(r.value or 0)} for r in res.all()]
        return {"series": series, "window": {"start": str(start_dt), "end": str(end_dt)}}

@router.get("/api/series/ratings")
async def api_series_ratings(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Daily average rating."""
    start_dt, end_dt = _range_or_default(start, end)
    async with get_session() as session:
        date_col = _date_col()
        stmt = (
            select(date_col.label("date"), func.avg(Review.rating).label("value"))
            .where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
            .group_by("date")
            .order_by("date")
        )
        res = await session.execute(stmt)
        series = [{"date": str(r.date), "value": round(float(r.value or 0.0), 3)} for r in res.all()]
        return {"series": series, "window": {"start": str(start_dt), "end": str(end_dt)}}

@router.get("/api/sentiment/series")
async def api_sentiment_series(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Daily average sentiment score (with fallback to rating-derived proxy for NULLs)."""
    start_dt, end_dt = _range_or_default(start, end)
    async with get_session() as session:
        date_col = _date_col()
        avg_sent_expr = func.avg(func.coalesce(Review.sentiment_score, _rating_sent_fallback()))
        stmt = (
            select(date_col.label("date"), avg_sent_expr.label("value"))
            .where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
            .group_by("date")
            .order_by("date")
        )
        res = await session.execute(stmt)
        series = [{"date": str(r.date), "value": round(float(r.value or 0.0), 3)} for r in res.all()]
        return {"series": series, "window": {"start": str(start_dt), "end": str(end_dt)}}

@router.get("/api/series/overview")
async def api_series_overview(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Return all three series in one call."""
    vol = await api_series_reviews(company_id, start, end)
    rat = await api_series_ratings(company_id, start, end)
    sen = await api_sentiment_series(company_id, start, end)
    return {
        "volume": vol["series"],
        "rating": rat["series"],
        "sentiment": sen["series"],
        "window": vol["window"],
    }

# ──────────────────────────────────────────────────────────────────────────────
# Departmental / Aspects Insights
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/aspects/avg")
async def api_aspects_average(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Departmental aspects average values."""
    start_dt, end_dt = _range_or_default(start, end)
    async with get_session() as session:
        date_col = _date_col()
        stmt = (
            select(
                func.avg(Review.aspect_rooms).label("rooms"),
                func.avg(Review.aspect_staff).label("staff"),
                func.avg(Review.aspect_cleanliness).label("cleanliness"),
                func.avg(Review.aspect_value).label("value"),
                func.avg(Review.aspect_location).label("location"),
                func.avg(Review.aspect_food).label("food"),
            )
            .where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
        )
        row = (await session.execute(stmt)).first()
        aspects = {
            "rooms": round(float(row.rooms or 0.0), 3),
            "staff": round(float(row.staff or 0.0), 3),
            "cleanliness": round(float(row.cleanliness or 0.0), 3),
            "value": round(float(row.value or 0.0), 3),
            "location": round(float(row.location or 0.0), 3),
            "food": round(float(row.food or 0.0), 3),
        }
        vals = [v for v in aspects.values() if v > 0]
        global_avg = (sum(vals) / len(vals)) if vals else 0.0
        strengths = sorted([k for k, v in aspects.items() if v >= max(global_avg, 0.6)], key=lambda k: -aspects[k])
        weaknesses = sorted([k for k, v in aspects.items() if 0 < v < max(global_avg, 0.6)], key=lambda k: aspects[k])
        ranked = sorted(aspects.items(), key=lambda kv: -kv[1])
        return {
            "aspects": aspects,
            "ranked": ranked,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "global_avg": round(global_avg, 3),
            "window": {"start": str(start_dt), "end": str(end_dt)},
        }

# ──────────────────────────────────────────────────────────────────────────────
# Operational Overview + Legacy Shim
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/operational/overview")
async def api_operational_overview(company_id: int, start: Optional[str] = None, end: Optional[str] = None, limit_urgent: int = Query(10, ge=1, le=50)):
    """Operational overview with urgent issues."""
    start_dt, end_dt = _range_or_default(start, end)
    async with get_session() as session:
        date_col = _date_col()
        total = (await session.execute(
            select(func.count(Review.id)).where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
        )).scalar() or 0
        complaints = (await session.execute(
            select(func.count(Review.id)).where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt, Review.is_complaint == True))
        )).scalar() or 0
        praise = (await session.execute(
            select(func.count(Review.id)).where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt, Review.is_praise == True))
        )).scalar() or 0
        complaint_rate = round((complaints / total) * 100, 1) if total else 0.0
        praise_rate = round((praise / total) * 100, 1) if total else 0.0
        urgent_stmt = (
            select(
                Review.id, Review.author_name, Review.rating, Review.text,
                Review.sentiment_score, Review.google_review_time, Review.profile_photo_url
            )
            .where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
            .order_by(desc(Review.google_review_time))
            .limit(500)
        )
        urgent_rows = (await session.execute(urgent_stmt)).all()
        urgent_items = []
        for r in urgent_rows:
            text = r.text or ""
            s_label = _sentiment_label(r.sentiment_score)
            has_urgent_kw = any(term in text.lower() for term in _URGENT_TERMS)
            is_urgent = (
                (r.rating is not None and r.rating <= 2) or
                (r.sentiment_score is not None and r.sentiment_score <= -0.5) or
                has_urgent_kw
            )
            if is_urgent:
                urgent_items.append({
                    "review_id": r.id,
                    "author_name": r.author_name or "Anonymous",
                    "rating": r.rating,
                    "sentiment_score": round(float(r.sentiment_score or 0.0), 3),
                    "sentiment_label": s_label,
                    "review_time": r.google_review_time.strftime("%Y-%m-%d") if r.google_review_time else "",
                    "text": text[:1200],
                    "profile_photo_url": r.profile_photo_url or "",
                    "urgent_reason": {
                        "low_rating": bool(r.rating is not None and r.rating <= 2),
                        "very_negative_sentiment": bool(r.sentiment_score is not None and r.sentiment_score <= -0.5),
                        "keyword_flag": bool(has_urgent_kw),
                    },
                })
            if len(urgent_items) >= limit_urgent:
                break
        return {
            "total_reviews": int(total),
            "complaint_count": int(complaints),
            "complaint_rate": complaint_rate,
            "praise_count": int(praise),
            "praise_rate": praise_rate,
            "urgent_issues": urgent_items,
            "window": {"start": str(start_dt), "end": str(end_dt)},
        }

@router.get("/api/complaints/stats")
async def api_complaints_stats(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """
    Legacy endpoint shim for frontends that still call /api/complaints/stats.
    Wraps /api/operational/overview to return the expected shape.
    """
    op = await api_operational_overview(company_id, start, end, limit_urgent=0)
    return {
        "total_reviews": op.get("total_reviews", 0),
        "complaint_count": op.get("complaint_count", 0),
        "complaint_rate": op.get("complaint_rate", 0.0),
        "praise_count": op.get("praise_count", 0),
        "praise_rate": op.get("praise_rate", 0.0),
        "window": op.get("window"),
    }

# ──────────────────────────────────────────────────────────────────────────────
# Themes & Keywords
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/keywords/themes")
async def api_keywords_themes(company_id: int, start: Optional[str] = None, end: Optional[str] = None, limit: int = Query(12, ge=5, le=40)):
    """Top unigrams & bigrams + emerging topics (last 7d vs previous 7d)."""
    start_dt, end_dt = _range_or_default(start, end)
    prev7_end = end_dt - timedelta(days=NEW_REVIEW_DAYS)
    prev7_start = prev7_end - timedelta(days=NEW_REVIEW_DAYS - 1)
    async with get_session() as session:
        date_col = _date_col()
        rows = (await session.execute(
            select(Review.text, Review.sentiment_score, Review.google_review_time)
            .where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
            .order_by(desc(Review.google_review_time))
            .limit(5000)
        )).all()
    if not rows:
        return {"positive_keywords": [], "negative_keywords": [], "top_bigrams": [], "emerging": [], "window": {"start": str(start_dt), "end": str(end_dt)}}
    tokens_all: List[str] = []
    bigrams_all: List[str] = []
    tokens_times: List[Optional[datetime]] = []
    for text, sent, ts in rows:
        if not text:
            continue
        tokens = _clean_tokens(text)
        tokens_all.extend(tokens)
        bigrams_all.extend(_bigrams(tokens))
        tokens_times.extend([ts] * len(tokens))
    unigram_counter = Counter(tokens_all)
    bigram_counter = Counter(bigrams_all)
    positives = [w for w, _ in unigram_counter.most_common(limit * 3) if w in _POSITIVE_HINTS]
    negatives = [w for w, _ in unigram_counter.most_common(limit * 3) if w in _NEGATIVE_HINTS]
    top_bigrams = [bg for bg, _ in bigram_counter.most_common(limit * 3) if all(t not in _STOPWORDS for t in bg.split())]
    last7_start = end_dt - timedelta(days=NEW_REVIEW_DAYS - 1)
    def _count_in_period(items: List[str], s: date, e: date, stamps: List[Optional[datetime]]) -> Counter:
        c = Counter()
        for w, ts in zip(items, stamps):
            if ts is None: continue
            d = ts.date()
            if s <= d <= e: c[w] += 1
        return c
    last7_counts = _count_in_period(tokens_all, last7_start, end_dt, tokens_times)
    prev7_counts = _count_in_period(tokens_all, prev7_start, prev7_end, tokens_times)
    emerging_scores = []
    for w, cnt in last7_counts.items():
        if w in _STOPWORDS or len(w) <= 2:
            continue
        prev_cnt = prev7_counts.get(w, 0)
        if cnt >= 2 and cnt >= prev_cnt * 1.5 + 1:
            emerging_scores.append((w, cnt - prev_cnt))
    emerging = [w for w, _ in sorted(emerging_scores, key=lambda x: -x[1])[:limit]]
    return {
        "positive_keywords": positives[:limit],
        "negative_keywords": negatives[:limit],
        "top_bigrams": top_bigrams[:limit],
        "emerging": emerging,
        "window": {"start": str(start_dt), "end": str(end_dt)},
    }

# ──────────────────────────────────────────────────────────────────────────────
# AI Recommendations + Executive Summary
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/ai/recommendations")
async def api_ai_recommendations(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Actionable recommendations based on KPIs, aspects, ops."""
    kpis = await api_kpis(company_id, start, end)
    aspects = await api_aspects_average(company_id, start, end)
    ops = await api_operational_overview(company_id, start, end, limit_urgent=5)
    rating = kpis["avg_rating"]
    sentiment = kpis["avg_sentiment"]
    total = kpis["total_reviews"]
    complaint_rate = ops["complaint_rate"]
    strengths = aspects["strengths"]
    weaknesses = aspects["weaknesses"]
    recs: List[str] = []
    if total < 30:
        recs.append("Increase review velocity: trigger post-visit SMS/email nudges and add QR prompts at checkout.")
    elif kpis["new_reviews"] < 5:
        recs.append("New reviews slowed this week. Run a small incentive campaign to boost fresh feedback.")
    if rating >= 4.2 and sentiment < 0.1:
        recs.append("Address text-level frustrations despite high stars: audit pricing transparency and staff communication.")
    if rating < 4.0 and sentiment >= 0.25:
        recs.append("Guests are positive in text but penalize stars—review pricing, expectations, and listing visuals.")
    if complaint_rate >= 25.0:
        recs.append("Complaint rate is high: enable same-day outreach to negative reviewers and create a visible resolution flow.")
    if ops["urgent_issues"]:
        recs.append("Triage urgent issues flagged (safety/legal keywords or very negative sentiment) within 24 hours.")
    if weaknesses:
        recs.append(f"Prioritize weakest departments: {', '.join(w.upper() for w in weaknesses[:3])}—set 2-week improvement targets.")
    if strengths:
        recs.append(f"Amplify strengths ({', '.join(strengths[:2])}) in marketing copy and replies to build trust.")
    recs.append("Establish a weekly review stand-up: review trends, respond to 100% negatives, and A/B test service fixes.")
    health_score = round(((rating / 5.0) * 0.5 + ((sentiment + 1.0) / 2.0) * 0.5) * 100, 1)
    verdict = "Steady Growth"
    if sentiment < 0.1 and rating > 4.0:
        verdict = "Critical Disconnect"
    elif sentiment > 0.4 and rating < 4.0:
        verdict = "Hidden Potential"
    elif rating < 3.5:
        verdict = "Crisis Mode"
    return {
        "verdict": verdict,
        "business_health_score": health_score,
        "top_action_items": recs[:6],
        "window": kpis["window"],
    }

@router.get("/api/ai/executive-summary")
async def api_ai_executive_summary(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """
    Human-friendly executive summary that blends KPIs, aspects, operational stats,
    alerts and themes into one narrative paragraph + highlights.
    """
    kpis = await api_kpis(company_id, start, end)
    aspects = await api_aspects_average(company_id, start, end)
    ops = await api_operational_overview(company_id, start, end, limit_urgent=5)
    alerts = await api_alerts(company_id, start, end)
    themes = await api_keywords_themes(company_id, start, end, limit=8)
    recs = await api_ai_recommendations(company_id, start, end)
    w = kpis["window"]
    strengths = aspects.get("strengths", [])
    weaknesses = aspects.get("weaknesses", [])
    pos_kw = themes.get("positive_keywords", [])[:5]
    neg_kw = themes.get("negative_keywords", [])[:5]
    summary = (
        f"From {w['start']} to {w['end']}, we analyzed {kpis['total_reviews']} reviews. "
        f"Average rating is {kpis['avg_rating']:.1f} with average sentiment {kpis['avg_sentiment']:.3f}. "
        f"New reviews in the latest week: {kpis['new_reviews']}. "
        f"Operationally, complaint rate is {ops['complaint_rate']:.1f}% across {ops['total_reviews']} total reviews. "
        f"Aspects suggest strengths in {', '.join(strengths[:2]) if strengths else 'no clear strengths'} "
        f"and weaknesses in {', '.join(weaknesses[:2]) if weaknesses else 'no obvious gaps'}. "
        f"Top positive themes: {', '.join(pos_kw) if pos_kw else '—'}; pain points: {', '.join(neg_kw) if neg_kw else '—'}. "
        f"Overall verdict: {recs['verdict']}; Business Health Score: {recs['business_health_score']}."
    )
    highlights = []
    for a in alerts.get("alerts", []):
        highlights.append(f"{a.get('type','alert').replace('_',' ').title()}: {a.get('message','')}")
    return {
        "summary": summary,
        "highlights": highlights[:6],
        "top_actions": recs.get("top_action_items", []),
        "window": w,
    }

# ──────────────────────────────────────────────────────────────────────────────
# Recent Feedback Feed (annotated) + List
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/reviews/feed")
async def api_reviews_feed(company_id: int, start: Optional[str] = None, end: Optional[str] = None, limit: int = Query(50, ge=5, le=200)):
    """Recent reviews with annotations."""
    start_dt, end_dt = _range_or_default(start, end)
    async with get_session() as session:
        date_col = _date_col()
        stmt = (
            select(
                Review.id, Review.author_name, Review.rating, Review.sentiment_score, Review.text,
                Review.google_review_time, Review.profile_photo_url
            )
            .where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
            .order_by(desc(Review.google_review_time))
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
    items = []
    for r in rows:
        text = (r.text or "")[:2000]
        tokens = _clean_tokens(text)
        s_label = _sentiment_label(r.sentiment_score)
        detected = sorted({t for t in tokens if (t in _POSITIVE_HINTS or t in _NEGATIVE_HINTS)})
        is_urgent = (
            (r.rating is not None and r.rating <= 2) or
            (r.sentiment_score is not None and r.sentiment_score <= -0.5) or
            any(term in text.lower() for term in _URGENT_TERMS)
        )
        items.append({
            "review_id": r.id,
            "author_name": r.author_name or "Anonymous",
            "rating": r.rating,
            "sentiment_score": round(float(r.sentiment_score or 0.0), 3),
            "sentiment_label": s_label,
            "review_time": r.google_review_time.strftime("%Y-%m-%d") if r.google_review_time else "",
            "text": text,
            "profile_photo_url": r.profile_photo_url or "",
            "is_urgent": is_urgent,
            "detected_topics": detected[:8],
        })
    return {"items": items, "window": {"start": str(start_dt), "end": str(end_dt)}}

@router.get("/api/reviews/list")
async def api_reviews_list(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    start_dt, end_dt = _range_or_default(start, end)
    async with get_session() as session:
        date_col = _date_col()
        res = await session.execute(
            select(Review).where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt)).order_by(desc(Review.google_review_time))
        )
        items = res.scalars().all()
        return {
            "items": [{
                "author_name": r.author_name or "Anonymous",
                "rating": r.rating,
                "text": r.text or "",
                "sentiment_score": round(float(r.sentiment_score or 0.0), 3),
                "review_time": r.google_review_time.strftime("%Y-%m-%d") if r.google_review_time else "",
                "profile_photo_url": r.profile_photo_url or "",
            } for r in items],
            "window": {"start": str(start_dt), "end": str(end_dt)},
        }

# ──────────────────────────────────────────────────────────────────────────────
# Predictive Alerts
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/alerts")
async def api_alerts(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """
    Trend-based alerts using two-window comparisons (last7 vs prev7).
    """
    start_dt, end_dt = _range_or_default(start, end)
    last7_start = end_dt - timedelta(days=NEW_REVIEW_DAYS - 1)
    prev7_end = last7_start - timedelta(days=1)
    prev7_start = prev7_end - timedelta(days=NEW_REVIEW_DAYS - 1)
    kpis = await api_kpis(company_id, start, end)
    ops = await api_operational_overview(company_id, start, end, limit_urgent=5)
    vol = await api_series_reviews(company_id, start, end)
    vol_map = {s["date"]: s["value"] for s in vol["series"]}
    def _sum_in(a: date, b: date) -> int:
        return sum(vol_map.get(str(a + timedelta(days=i)), 0) for i in range((b - a).days + 1))
    last7 = _sum_in(last7_start, end_dt)
    prev7 = _sum_in(prev7_start, prev7_end)
    alerts = []
    if prev7 >= 8 and last7 <= prev7 * 0.6:
        alerts.append({"type": "volume_drop", "severity": "high", "message": f"Review volume down {round(100 - (last7 / max(prev7,1))*100)}% vs prior week."})
    rat_series = await api_series_ratings(company_id, start, end)
    sen_series = await api_sentiment_series(company_id, start, end)
    def _avg_in(series: List[Dict], a: date, b: date) -> float:
        vals = [s["value"] for s in series if a <= datetime.strptime(s["date"], "%Y-%m-%d").date() <= b]
        return round(sum(vals) / len(vals), 3) if vals else 0.0
    rating_last7 = _avg_in(rat_series["series"], last7_start, end_dt)
    rating_prev7 = _avg_in(rat_series["series"], prev7_start, prev7_end)
    if rating_prev7 > 0 and rating_last7 <= rating_prev7 - 0.3:
        alerts.append({"type": "rating_dip", "severity": "medium", "message": f"Avg rating dropped {round(rating_prev7 - rating_last7, 2)} vs prior week."})
    sentiment_last7 = _avg_in(sen_series["series"], last7_start, end_dt)
    sentiment_prev7 = _avg_in(sen_series["series"], prev7_start, prev7_end)
    if sentiment_prev7 > 0 and sentiment_last7 <= sentiment_prev7 - 0.1:
        alerts.append({"type": "sentiment_dip", "severity": "medium", "message": f"Avg sentiment dropped {round(sentiment_prev7 - sentiment_last7, 3)} vs prior week."})
    if ops["complaint_rate"] >= 30.0 and kpis["total_reviews"] >= 20:
        alerts.append({"type": "complaint_spike", "severity": "high", "message": "Complaint rate exceeded 30% this period. Immediate triage recommended."})
    if kpis["new_reviews"] == 0:
        alerts.append({"type": "review_drought", "severity": "low", "message": "No new reviews in the last 7 days."})
    return {
        "alerts": alerts,
        "context": {
            "last7_volume": last7,
            "prev7_volume": prev7,
            "rating_last7": rating_last7,
            "rating_prev7": rating_prev7,
            "sentiment_last7": sentiment_last7,
            "sentiment_prev7": sentiment_prev7,
        },
        "window": {"start": str(start_dt), "end": str(end_dt)},
    }
