# filename: review_saas/app/routes/dashboard.py
from __future__ import annotations
import io
import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import Date, and_, case, cast, desc, func, select
from starlette.templating import Jinja2Templates

from app.core.db import get_session
from app.core.models import Company, Review
from app.routes.companies import _require_user

router = APIRouter(tags=["dashboard"])  # legacy + v2 endpoints live here as well
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
    "has", "have", "had", "do", "did", "does", "just", "also", "than", "then", "there", "here",
    "about", "into", "out", "over", "under", "between", "after", "before", "during", "more", "most",
    "less", "least", "again", "ever", "never", "always", "some", "any", "much", "many", "few", "lot", "lots"
}
_POSITIVE_HINTS = {
    "great", "excellent", "good", "friendly", "clean", "amazing", "love", "nice", "comfortable",
    "helpful", "fast", "quick", "tasty", "spacious", "professional", "responsive", "polite",
    "courteous", "beautiful", "quiet", "safe", "affordable", "fair", "recommend", "recommended",
    "awesome", "perfect", "best", "delicious", "fresh", "warm", "welcoming", "cleanliness", "hygienic"
}
_NEGATIVE_HINTS = {
    "bad", "poor", "worst", "slow", "dirty", "rude", "problem", "issue", "disappointed",
    "expensive", "noisy", "crowded", "delay", "broken", "smelly", "cold", "hot", "late",
    "unprofessional", "unhelpful", "refund", "fraud", "scam", "unsafe", "hygiene", "lawsuit",
    "legal", "threat", "hazard", "poison", "sick", "expired", "fire", "electrical", "incompetent", "overpriced"
}
_URGENT_TERMS = {
    "refund", "fraud", "scam", "unsafe", "health", "hygiene", "lawsuit", "legal", "threat",
    "hazard", "poison", "sick", "food poisoning", "expired", "broken glass", "fire", "electrical"
}

# --- Basic parsing helpers ----------------------------------------------------
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
    cleaned = re.sub(r"[^a-zA-Z\s]", " ", (text or "").lower())
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
# Lightweight NLP + Analytics (embedded here so you don't need another module)
# ──────────────────────────────────────────────────────────────────────────────
TOKEN_RE = re.compile(r"[a-zA-Z]+")

@dataclass
class KeywordScore:
    term: str
    freq: int
    avg_sent: float
    contribution: float  # freq * avg_sent
    delta: int = 0       # last7 - prev7 frequency

# Small polarity lexicon (extendable)
_LEX_POS = {
    "great":4, "excellent":5, "good":3, "friendly":3, "clean":2, "amazing":4, "love":4, "nice":2,
    "comfortable":3, "helpful":3, "fast":2, "quick":2, "tasty":3, "spacious":2, "professional":3,
    "responsive":3, "polite":2, "courteous":2, "beautiful":3, "quiet":2, "safe":2, "affordable":2,
    "fair":2, "recommend":3, "recommended":3, "awesome":4, "perfect":4, "best":4, "delicious":4,
    "fresh":2, "warm":1, "welcoming":2, "cleanliness":3, "hygienic":3
}
_LEX_NEG = {
    "bad":-3, "poor":-3, "worst":-5, "slow":-2, "dirty":-3, "rude":-4, "problem":-2, "issue":-2,
    "disappointed":-3, "expensive":-2, "noisy":-2, "crowded":-2, "delay":-2, "delayed":-2, "broken":-3,
    "smelly":-3, "cold":-1, "hot":-1, "late":-2, "unprofessional":-4, "unhelpful":-3, "refund":-3,
    "fraud":-5, "scam":-5, "unsafe":-4, "hygiene":-2, "lawsuit":-4, "legal":-2, "threat":-4, "hazard":-4,
    "poison":-5, "sick":-3, "expired":-3, "fire":-3, "electrical":-2, "incompetent":-4, "overpriced":-3
}
_LEXICON = {**_LEX_POS, **_LEX_NEG}

def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    tokens = [t.lower() for t in TOKEN_RE.findall(text)]
    return [t for t in tokens if len(t) > 2 and t not in _STOPWORDS]

def _bigrams2(tokens: List[str]) -> List[str]:
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)]

def _clamp(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))

def _lexicon_sentiment(tokens: List[str]) -> float:
    if not tokens:
        return 0.0
    score = 0.0
    for t in tokens:
        score += _LEXICON.get(t, 0)
    norm = score / max(1.0, math.sqrt(len(tokens)))
    return _clamp(norm / 5.0, -1.0, 1.0)

def _safe_sentiment(text: str, rating: Optional[int] = None, fallback_weight: float = 0.35) -> float:
    toks = _tokenize(text or "")
    lex = _lexicon_sentiment(toks)
    if rating is None:
        return lex
    rate_proxy = {5: 0.8, 4: 0.4, 3: 0.0, 2: -0.4, 1: -0.8}.get(int(rating), 0.0)
    return _clamp((1 - fallback_weight) * lex + fallback_weight * rate_proxy, -1.0, 1.0)

def _label_from_score(score: float) -> str:
    if score >= 0.35:
        return "positive"
    if score <= -0.25:
        return "negative"
    return "neutral"

def _keyword_attribution(
    docs: Iterable[Tuple[str, Optional[float], Optional[int], Optional[datetime]]],
    last7: Tuple[date, date],
    prev7: Tuple[date, date],
    top_n: int = 20,
) -> Dict[str, List[KeywordScore]]:
    token_counts: Counter = Counter()
    token_sent_sum: Dict[str, float] = defaultdict(float)
    token_times: List[Tuple[str, Optional[datetime]]] = []

    for text, sent, rating, ts in docs:
        if not text:
            continue
        toks = _tokenize(text)
        s = sent if sent is not None else _safe_sentiment(text, rating)
        for t in toks:
            token_counts[t] += 1
            token_sent_sum[t] += s
            token_times.append((t, ts))

    scores: List[KeywordScore] = []
    for term, freq in token_counts.items():
        avg = (token_sent_sum[term] / max(1, freq))
        scores.append(KeywordScore(term=term, freq=int(freq), avg_sent=float(avg), contribution=float(avg*freq)))

    l7s, l7e = last7
    p7s, p7e = prev7
    last7_c = Counter()
    prev7_c = Counter()
    for t, ts in token_times:
        if not ts:
            continue
        d = ts.date()
        if l7s <= d <= l7e:
            last7_c[t] += 1
        elif p7s <= d <= p7e:
            prev7_c[t] += 1
    growth = {t: last7_c.get(t, 0) - prev7_c.get(t, 0) for t in token_counts.keys()}

    for s in scores:
        s.delta = growth.get(s.term, 0)

    positive = sorted([s for s in scores if s.avg_sent > 0], key=lambda x: (x.contribution, x.freq), reverse=True)[:top_n]
    negative = sorted([s for s in scores if s.avg_sent < 0], key=lambda x: (abs(x.contribution), x.freq), reverse=True)[:top_n]
    emerging = sorted([s for s in scores if s.delta > 0 and s.freq >= 2], key=lambda x: (x.delta, x.freq), reverse=True)[:top_n]

    return {
        "positive": positive,
        "negative": negative,
        "emerging": emerging,
    }

def _top_bigrams_docs(docs: Iterable[str], top_n: int = 20) -> List[Tuple[str, int]]:
    counter = Counter()
    for text in docs:
        toks = _tokenize(text or "")
        for bg in _bigrams2(toks):
            w1, w2 = bg.split()
            if w1 in _STOPWORDS or w2 in _STOPWORDS:
                continue
            counter[bg] += 1
    return counter.most_common(top_n)

# ──────────────────────────────────────────────────────────────────────────────
# Dashboard Page (UPDATED: now passes companies + active_company_id)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, company_id: Optional[int] = Query(None)):
    """
    Render authenticated dashboard page with company list and an active company id.
    If company_id is not provided, default to the first company (if available).
    """
    uid = _require_user(request)
    if not uid:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Session expired."})

    async with get_session() as session:
        # Adjust the filter below if you have tenant/user scoping for companies.
        companies = (await session.execute(select(Company).order_by(Company.name))).scalars().all()

    active_company_id: Optional[int] = None
    if company_id:
        active_company_id = int(company_id)
    elif companies:
        active_company_id = int(companies[0].id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "companies": companies,
            "active_company_id": active_company_id,
        },
    )

# ──────────────────────────────────────────────────────────────────────────────
# KPIs & Ratings (unchanged)
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
# Trends (Volume, Rating, Sentiment) — unchanged
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
# Departmental / Aspects Insights (unchanged)
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
# Operational Overview + Legacy Shim (unchanged)
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
# Themes & Keywords (unchanged v1)
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
    def _count_in_period_local(items: List[str], s: date, e: date, stamps: List[Optional[datetime]]) -> Counter:
        c = Counter()
        for w, ts in zip(items, stamps):
            if ts is None: continue
            d = ts.date()
            if s <= d <= e: c[w] += 1
        return c
    last7_counts = _count_in_period_local(tokens_all, last7_start, end_dt, tokens_times)
    prev7_counts = _count_in_period_local(tokens_all, prev7_start, prev7_end, tokens_times)
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
# AI Recommendations + Executive Summary (v1, unchanged)
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
    Adds `conclusion` and `rationale` fields without breaking existing keys.
    """
    kpis = await api_kpis(company_id, start, end)
    aspects = await api_aspects_average(company_id, start, end)
    ops = await api_operational_overview(company_id, start, end, limit_urgent=5)
    alerts = await api_alerts(company_id, start, end)
    themes = await api_keywords_themes(company_id, start, end, limit=8)
    # Use v2 sentiment summary to compute conclusion & confidence
    sent_v2 = await sentiment_summary_v2(company_id, start, end)  # defined below
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

    # Conclusion & rationale from v2 sentiment
    avg = float(sent_v2.get("avg", 0.0))
    ci = sent_v2.get("ci95", [0.0, 0.0])
    total = sum(sent_v2.get("counts", {}).values()) or 0

    conclusion = "On Track"
    if avg <= -0.15:
        conclusion = "Needs Immediate Attention"
    elif avg < 0.1:
        conclusion = "Needs Attention"
    elif avg > 0.45 and total >= 50:
        conclusion = "Strong Momentum"

    rationale = []
    ci_width = abs(ci[1] - ci[0]) if isinstance(ci, list) and len(ci) == 2 else 0.0
    if ci_width > 0.25:
        rationale.append("Sentiment confidence is low (wide 95% CI). Collect more reviews to reduce uncertainty.")
    counts = sent_v2.get("counts", {"negative": 0, "neutral": 0, "positive": 0})
    if counts.get("negative", 0) >= max(5, 0.25 * total):
        rationale.append("Negative share is elevated; triage root-cause themes.")

    highlights = []
    for a in alerts.get("alerts", []):
        highlights.append(f"{a.get('type','alert').replace('_',' ').title()}: {a.get('message','')}")

    return {
        "summary": summary,
        "highlights": highlights[:6],
        "top_actions": recs.get("top_action_items", []),
        "window": w,
        "conclusion": conclusion,
        "rationale": rationale,
        "sentiment_ci95": ci,
    }

# ──────────────────────────────────────────────────────────────────────────────
# Recent Feedback Feed (annotated) + List (UPDATED: sort support)
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
async def api_reviews_list(
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    sort: Optional[str] = Query("newest", regex="^(newest|oldest|highest|lowest)$")
):
    """
    Returns a simple list of reviews constrained by date window with sorting.
    sort:
      - newest  -> google_review_time DESC
      - oldest  -> google_review_time ASC
      - highest -> rating DESC, time DESC
      - lowest  -> rating ASC, time DESC
    """
    start_dt, end_dt = _range_or_default(start, end)

    # Build ordering
    date_col = _date_col()
    if sort == "oldest":
        order = [date_col.asc()]
    elif sort == "highest":
        order = [Review.rating.desc().nullslast(), date_col.desc()]
    elif sort == "lowest":
        order = [Review.rating.asc().nullslast(), date_col.desc()]
    else:  # newest
        order = [date_col.desc()]

    async with get_session() as session:
        res = await session.execute(
            select(Review)
            .where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
            .order_by(*order)
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
# Predictive Alerts (unchanged)
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
        pct = round(100 - (last7 / max(prev7,1))*100)
        alerts.append({"type": "volume_drop", "severity": "high", "message": f"Review volume down {pct}% vs prior week."})
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

# ──────────────────────────────────────────────────────────────────────────────
# NEW v2 Endpoints — comprehensive sentiment, keywords, time breakdown, PNG
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/v2/sentiment/summary")
async def sentiment_summary_v2(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    s, e = _range_or_default(start, end)
    async with get_session() as session:
        dc = _date_col()
        rows = (await session.execute(
            select(Review.text, Review.sentiment_score, Review.rating, Review.google_review_time)
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
            .order_by(desc(Review.google_review_time))
            .limit(10000)
        )).all()

    if not rows:
        return {
            "window": {"start": str(s), "end": str(e)},
            "counts": {"positive": 0, "neutral": 0, "negative": 0},
            "avg": 0.0,
            "ci95": [0.0, 0.0],
            "coverage": {"stored": 0, "fallback": 0}
        }

    vals: List[float] = []
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    stored = 0
    fallback = 0

    for text, ss, rating, _ts in rows:
        if ss is None:
            score = _safe_sentiment(text or "", rating)
            fallback += 1
        else:
            score = float(ss)
            stored += 1
        vals.append(score)
        counts[_label_from_score(score)] += 1

    n = len(vals)
    avg = sum(vals) / n
    var = sum((v - avg) ** 2 for v in vals) / max(1, (n - 1))
    sd = math.sqrt(var)
    se = sd / math.sqrt(n) if n > 0 else 0.0
    ci95 = [avg - 1.96 * se, avg + 1.96 * se]

    return {
        "window": {"start": str(s), "end": str(e)},
        "counts": counts,
        "avg": round(avg, 3),
        "ci95": [round(ci95[0], 3), round(ci95[1], 3)],
        "coverage": {"stored": stored, "fallback": fallback}
    }

@router.get("/api/v2/keywords")
async def keywords_v2(
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(20, ge=5, le=50),
):
    s, e = _range_or_default(start, end)
    l7s = e - timedelta(days=NEW_REVIEW_DAYS - 1)
    p7e = l7s - timedelta(days=1)
    p7s = p7e - timedelta(days=NEW_REVIEW_DAYS - 1)

    async with get_session() as session:
        dc = _date_col()
        rows = (await session.execute(
            select(Review.text, Review.sentiment_score, Review.rating, Review.google_review_time)
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
            .order_by(desc(Review.google_review_time))
            .limit(10000)
        )).all()

    docs = [(t, ss, r, ts) for (t, ss, r, ts) in rows if t]
    if not docs:
        return {
            "window": {"start": str(s), "end": str(e)},
            "positive": [],
            "negative": [],
            "emerging": [],
            "bigrams": []
        }

    kw = _keyword_attribution(docs, (l7s, e), (p7s, p7e), top_n=limit)
    bigs = _top_bigrams_docs([d[0] for d in docs], top_n=limit)

    def _cast(items: List[KeywordScore]):
        return [{"term": x.term, "freq": x.freq, "avg_sent": round(x.avg_sent, 3), "contribution": round(x.contribution, 3), "delta": x.delta} for x in items]

    return {
        "window": {"start": str(s), "end": str(e)},
        "positive": _cast(kw["positive"]),
        "negative": _cast(kw["negative"]),
        "emerging": _cast(kw["emerging"]),
        "bigrams": [{"term": t, "freq": f} for (t, f) in bigs]
    }

@router.get("/api/v2/timebreakdown")
async def time_breakdown_v2(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    s, e = _range_or_default(start, end)
    async with get_session() as session:
        dc = _date_col()
        rows = (await session.execute(
            select(Review.google_review_time)
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
            .order_by(desc(Review.google_review_time))
            .limit(10000)
        )).all()

    dow = {i: 0 for i in range(7)}  # 0=Mon
    hod = {i: 0 for i in range(24)}
    for (ts,) in rows:
        if not ts:
            continue
        try:
            dt = ts if isinstance(ts, datetime) else datetime.combine(ts, datetime.min.time())
            dow[dt.weekday()] += 1
            hod[dt.hour] += 1
        except Exception:
            continue

    return {"window": {"start": str(s), "end": str(e)}, "day_of_week": dow, "hour_of_day": hod}

@router.get("/api/v2/ai/executive-summary")
async def executive_summary_v2(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Narrative summary with a deterministic conclusion and rationale."""
    sent = await sentiment_summary_v2(company_id, start, end)
    kw = await keywords_v2(company_id, start, end, limit=10)

    avg = float(sent["avg"])
    ci = sent["ci95"]
    total = sum(sent["counts"].values())

    conclusion = "On Track"
    if avg <= -0.15:
        conclusion = "Needs Immediate Attention"
    elif avg < 0.1:
        conclusion = "Needs Attention"
    elif avg > 0.45 and total >= 50:
        conclusion = "Strong Momentum"

    rationale = []
    ci_width = abs(ci[1] - ci[0])
    if ci_width > 0.25:
        rationale.append("Sentiment confidence is low (wide CI). Consider collecting more reviews.")
    if sent["counts"]["negative"] >= max(5, 0.25 * total):
        rationale.append("Negative share is elevated; triage root-cause themes below.")

    top_pos = [k["term"] for k in kw["positive"][:5]]
    top_neg = [k["term"] for k in kw["negative"][:5]]
    emerging = [k["term"] for k in kw["emerging"][:5]]

    summary = (
        f"Across {total} reviews, average sentiment is {avg:.3f} (95% CI {ci[0]:.3f}–{ci[1]:.3f}). "
        f"Positive: {sent['counts']['positive']}, Neutral: {sent['counts']['neutral']}, Negative: {sent['counts']['negative']}. "
        f"Key positives: {', '.join(top_pos) if top_pos else '—'}; key pain points: {', '.join(top_neg) if top_neg else '—'}. "
        f"Emerging topics: {', '.join(emerging) if emerging else '—'}."
    )

    return {
        "window": sent["window"],
        "summary": summary,
        "conclusion": conclusion,
        "rationale": rationale,
        "highlights": {
            "top_positive_keywords": top_pos,
            "top_negative_keywords": top_neg,
            "emerging_keywords": emerging,
        }
    }

@router.get("/api/v2/ai/recommendations")
async def recommendations_v2(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    sent = await sentiment_summary_v2(company_id, start, end)
    kw = await keywords_v2(company_id, start, end, limit=15)

    total = sum(sent["counts"].values())
    avg = float(sent["avg"])
    neg = kw["negative"]
    pos = kw["positive"]
    emerging = kw["emerging"]

    actions: List[str] = []

    if neg:
        top_drivers = [n["term"] for n in sorted(neg, key=lambda x: (abs(x["contribution"]), x["freq"]), reverse=True)[:5]]
        actions.append(f"Root-cause sprint on: {', '.join(top_drivers)}. Assign owners and 2-week targets.")

    if pos:
        top_strengths = [p["term"] for p in pos[:3]]
        actions.append(f"Amplify strengths in replies and listings: {', '.join(top_strengths)}.")

    if emerging:
        rising = [e["term"] for e in emerging[:5]]
        actions.append(f"Monitor rising topics: {', '.join(rising)}. Add them to weekly stand-up agenda.")

    if total < 30:
        actions.append("Increase review velocity: add post-visit nudges (SMS/email) and in-venue QR prompts.")
    if sent["counts"]["negative"] >= max(5, 0.25 * total):
        actions.append("Implement same-day outreach for negative reviews and track resolution SLAs.")
    if avg < 0.1:
        actions.append("Quick wins: pricing clarity, staff coaching, queue/time management, and cleanliness audits.")
    else:
        actions.append("Sustain momentum: celebrate wins publicly and codify good practices in SOPs.")

    prioritized = actions[:6]

    return {
        "window": sent["window"],
        "business_health": {
            "avg_sentiment": round(avg, 3),
            "n_reviews": total,
            "ci95": sent["ci95"]
        },
        "top_action_items": prioritized
    }

@router.get("/api/v2/charts/summary.png")
async def summary_png_v2(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Generates a compact PNG: sentiment share + top pos/neg keywords."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return Response(status_code=501, content=b"matplotlib not available", media_type="text/plain")

    sent = await sentiment_summary_v2(company_id, start, end)
    kw = await keywords_v2(company_id, start, end, limit=8)

    pos = kw["positive"][:8]
    neg = kw["negative"][:8]
    counts = sent["counts"]

    fig = plt.figure(figsize=(9, 4))
    gs = fig.add_gridspec(1, 3, wspace=0.35)

    # Pie
    ax0 = fig.add_subplot(gs[0, 0])
    labels = ["Pos", "Neu", "Neg"]
    vals = [counts.get("positive",0), counts.get("neutral",0), counts.get("negative",0)]
    colors = ["#2ecc71", "#bdc3c7", "#e74c3c"]
    if sum(vals) == 0:
        vals = [1, 0, 0]
    ax0.pie(vals, labels=labels, autopct="%1.0f%%", colors=colors, startangle=140)
    ax0.set_title("Sentiment Share")

    # Top positives
    ax1 = fig.add_subplot(gs[0, 1])
    terms_p = [x["term"] for x in pos][::-1]
    vals_p = [x["freq"] for x in pos][::-1]
    ax1.barh(terms_p, vals_p, color="#2ecc71")
    ax1.set_title("Top Positive")
    ax1.set_xlabel("Frequency")

    # Top negatives
    ax2 = fig.add_subplot(gs[0, 2])
    terms_n = [x["term"] for x in neg][::-1]
    vals_n = [x["freq"] for x in neg][::-1]
    ax2.barh(terms_n, vals_n, color="#e74c3c")
    ax2.set_title("Top Negative")
    ax2.set_xlabel("Frequency")

    buf = io.BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return Response(content=buf.read(), media_type="image/png")
