# filename: review_saas/app/routes/dashboard.py
from __future__ import annotations
import io
import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from typing import Dict, Iterable, List, Optional, Tuple, Any

from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse
from sqlalchemy import Date, and_, case, cast, desc, func, select, Integer, literal
from starlette.templating import Jinja2Templates

from app.core.db import get_session
from app.core.models import Company, Review
from app.routes.companies import _require_user

# NEW: integrate single-entity and competitor batch ingestion
try:
    from app.services.google_reviews import (
        ingest_company_reviews,
        ingest_multi_company_reviews,
        ReviewData as SvcReviewData,
        CompanyReviews as SvcCompanyReviews,
    )
except Exception as _svc_imp_err:
    ingest_company_reviews = None
    ingest_multi_company_reviews = None
    SvcReviewData = None
    SvcCompanyReviews = None

router = APIRouter(tags=["dashboard"])  # legacy + v2 endpoints live here as well
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.dashboard")

# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_DAYS = 30
NEW_REVIEW_DAYS = 7

# Rating → sentiment proxy (consistent for every site)
_RATING_PROXY = {5: 0.8, 4: 0.4, 3: 0.0, 2: -0.4, 1: -0.8}

_STOPWORDS = {
    # NOTE: keep "not" and "never" OUT of stopwords to enable Negation Logic
    "the", "and", "to", "a", "an", "in", "is", "it", "of", "for", "on", "was", "with", "at",
    "this", "that", "by", "be", "from", "as", "are", "were", "or", "we", "you", "they", "our",
    "your", "their", "but", "so", "if", "too", "very", "can", "could", "would", "will",
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

# Aspect keyword dictionaries (existing data for /api/aspects/sentiment)
_ASPECT_LEX = {
    "Service": {"service", "staff", "waiter", "host", "attendant", "attentive", "rude", "polite", "friendly", "unprofessional", "helpful"},
    "Product Quality": {"quality", "taste", "fresh", "stale", "clean", "hygiene", "delicious", "burnt", "undercooked", "spoiled"},
    "Pricing": {"price", "pricing", "expensive", "cheap", "affordable", "overpriced", "value", "cost"},
    "Delivery": {"delivery", "deliver", "delivered", "takeaway", "pickup", "late", "delay", "on time", "fast", "quick"},
}

# Canonicalized map for operational aspect trend endpoint (non‑breaking, new)
_ASPECT_TREND_CANON = {
    "Service": _ASPECT_LEX["Service"],
    "Product": _ASPECT_LEX["Product Quality"],  # map 'Product' → existing 'Product Quality' lex
    "Pricing": _ASPECT_LEX["Pricing"],
    "Delivery": _ASPECT_LEX["Delivery"],
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


def _date_col() -> Any:
    """DATE version for WHERE filters."""
    base = getattr(Review, "google_review_time", None)
    created = getattr(Review, "created_at", None)
    if base is not None and created is not None:
        return cast(func.coalesce(Review.google_review_time, Review.created_at), Date)
    return cast(Review.google_review_time, Date)


def _ts_col() -> Any:
    """TIMESTAMP version for date_trunc/group-by."""
    base = getattr(Review, "google_review_time", None)
    created = getattr(Review, "created_at", None)
    if base is not None and created is not None:
        return func.coalesce(Review.google_review_time, Review.created_at)
    return Review.google_review_time


# NOTE: New helper → default to LAST 30 DAYS unless start/end provided.
async def _auto_range_last30(company_id: int, start: Optional[str], end: Optional[str]) -> Tuple[date, date]:
    return _range_or_default(start, end, default_days=DEFAULT_DAYS)


def _rating_sent_fallback():
    """Robust fallback: cast rating to int to support string ratings and map to proxy sentiment."""
    r_int = cast(Review.rating, Integer)
    return case(
        (r_int == 5, _RATING_PROXY[5]),
        (r_int == 4, _RATING_PROXY[4]),
        (r_int == 3, _RATING_PROXY[3]),
        (r_int == 2, _RATING_PROXY[2]),
        (r_int == 1, _RATING_PROXY[1]),
        else_=0.0,
    )


def _sentiment_bucket_expr():
    """
    SQL expressions for final sentiment and pos/neu/neg counts.
    Treats 0.0 as missing by using NULLIF -> then COALESCE to fallback proxy.
    """
    s_expr = func.coalesce(func.nullif(Review.sentiment_score, 0.0), _rating_sent_fallback())
    pos = func.sum(case((s_expr >= 0.35, 1), else_=0))
    neg = func.sum(case((s_expr <= -0.25, 1), else_=0))
    total = func.count(Review.id)
    neu = total - pos - neg
    return s_expr, pos, neu, neg, total


def _sentiment_label(score: Optional[float]) -> str:
    if score is None:
        return "neutral"
    if score >= 0.35:
        return "positive"
    if score <= -0.25:
        return "negative"
    return "neutral"


# ──────────────────────────────────────────────────────────────────────────────
# Lightweight NLP + Analytics (embedded)
# ──────────────────────────────────────────────────────────────────────────────
TOKEN_RE = re.compile(r"[a-zA-Z]+")

# Negation words (for flipping nearby positive hints)
_NEGATORS = {"not", "never", "no", "hardly", "barely", "scarcely", "without", "lack", "lacking"}


@dataclass
class KeywordScore:
    term: str
    freq: int
    avg_sent: float
    contribution: float  # freq * avg_sent
    delta: int = 0  # last7 - prev7 frequency


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
    toks = [t.lower() for t in TOKEN_RE.findall(text)]
    out = []
    for t in toks:
        if len(t) <= 2:
            continue
        # keep negators even if they would otherwise be removed
        if t in _NEGATORS:
            out.append(t)
            continue
        if t in _STOPWORDS:
            continue
        out.append(t)
    return out


def _bigrams2(tokens: List[str]) -> List[str]:
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)]


def _clamp(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


def _lexicon_sentiment_with_negation(tokens: List[str]) -> float:
    """
    Sum lexicon scores, but flip positive terms if preceded by a negator
    within a small lookback window (up to 3 tokens).
    """
    if not tokens:
        return 0.0
    score = 0.0
    n = len(tokens)
    for i, t in enumerate(tokens):
        base = _LEXICON.get(t, 0)
        if base > 0:
            # Check if a negator appears in a small window BEFORE this token
            j0 = max(0, i - 3)
            if any(tokens[j] in _NEGATORS for j in range(j0, i)):
                base = -abs(base)  # flip polarity for positive hints
        # (We avoid flipping negative words—requirement is to flip positives.)
        score += base
    # normalize and clamp
    norm = score / max(1.0, math.sqrt(n))
    return _clamp(norm / 5.0, -1.0, 1.0)


def _safe_sentiment(text: str, rating: Optional[int] = None, fallback_weight: float = 0.35) -> float:
    toks = _tokenize(text or "")
    lex = _lexicon_sentiment_with_negation(toks)
    if rating is None:
        return lex
    rate_proxy = _RATING_PROXY.get(int(rating), 0.0)
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
        s = sent if (sent is not None and abs(float(sent)) >= 1e-9) else _safe_sentiment(text, rating)
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
        if not ts: continue
        d = ts.date()
        if l7s <= d <= l7e: last7_c[t] += 1
        elif p7s <= d <= p7e: prev7_c[t] += 1
    growth = {t: last7_c.get(t, 0) - prev7_c.get(t, 0) for t in token_counts.keys()}
    for s in scores:
        s.delta = growth.get(s.term, 0)
    positive = sorted([s for s in scores if s.avg_sent > 0], key=lambda x: (x.contribution, x.freq), reverse=True)[:top_n]
    negative = sorted([s for s in scores if s.avg_sent < 0], key=lambda x: (abs(x.contribution), x.freq), reverse=True)[:top_n]
    emerging = sorted([s for s in scores if s.delta > 0 and s.freq >= 2], key=lambda x: (x.delta, x.freq), reverse=True)[:top_n]
    return {"positive": positive, "negative": negative, "emerging": emerging}


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
# Dashboard + Links
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, company_id: Optional[int] = Query(None)):
    """
    Render authenticated dashboard page with company list and an active company id.
    Also injects a ready 'api_links' dict for use in the template if desired.
    """
    uid = _require_user(request)
    if not uid:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Session expired."})
    async with get_session() as session:
        companies = (await session.execute(select(Company).order_by(Company.name))).scalars().all()
    active_company_id: Optional[int] = None
    if company_id:
        active_company_id = int(company_id)
    elif companies:
        active_company_id = int(companies[0].id)
    api_links = {
        "kpis": "/api/kpis",
        "ratings_distribution": "/api/ratings/distribution",
        "sentiment_share": "/api/sentiment/share",
        "series_reviews": "/api/series/reviews",
        "series_ratings": "/api/series/ratings",
        "series_sentiment": "/api/sentiment/series",
        "trends": "/api/trends",
        "volume_vs_sentiment": "/api/volume-vs-sentiment",
        "correlation_rating_sentiment": "/api/correlation/rating-sentiment",
        "aspects_sentiment": "/api/aspects/sentiment",
        "aspects_avg": "/api/aspects/avg",
        "alerts": "/api/alerts",
        "operational": "/api/operational/overview",
        "reviews_list": "/api/reviews/list",
        "v2_keywords": "/api/v2/keywords",
        "v2_sentiment_summary": "/api/v2/sentiment/summary",
        "v2_exec_summary": "/api/v2/ai/executive-summary",
        "v2_recommendations": "/api/v2/ai/recommendations",
        "v2_summary_png": "/api/v2/charts/summary.png",
        # New (additive)
        "aspect_trend": "/api/operational/aspect-trend",
        "alert_email": "/api/alerts/high-severity-email",
        # NEW: external fetch + sync
        "external_reviews_fetch": "/api/external/google-reviews/fetch",
        "sync_reviews": "/api/companies/{company_id}/sync",
    }
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "companies": companies,
            "active_company_id": active_company_id,
            "api_links": api_links,
        },
    )


@router.get("/dashboard/links")
async def dashboard_links():
    """Simple machine‑readable map of dashboard API endpoints."""
    return JSONResponse({
        "kpis": "/api/kpis",
        "ratings_distribution": "/api/ratings/distribution",
        "sentiment_share": "/api/sentiment/share",
        "series_reviews": "/api/series/reviews",
        "series_ratings": "/api/series/ratings",
        "series_sentiment": "/api/sentiment/series",
        "trends": "/api/trends",
        "volume_vs_sentiment": "/api/volume-vs-sentiment",
        "correlation_rating_sentiment": "/api/correlation/rating-sentiment",
        "aspects_sentiment": "/api/aspects/sentiment",
        "aspects_avg": "/api/aspects/avg",
        "alerts": "/api/alerts",
        "operational": "/api/operational/overview",
        "reviews_list": "/api/reviews/list",
        "v2_keywords": "/api/v2/keywords",
        "v2_sentiment_summary": "/api/v2/sentiment/summary",
        "v2_exec_summary": "/api/v2/ai/executive-summary",
        "v2_recommendations": "/api/v2/ai/recommendations",
        "v2_summary_png": "/api/v2/charts/summary.png",
        # New
        "aspect_trend": "/api/operational/aspect-trend",
        "alert_email": "/api/alerts/high-severity-email",
        # NEW
        "external_reviews_fetch": "/api/external/google-reviews/fetch",
        "sync_reviews": "/api/companies/{company_id}/sync",
    })


# ──────────────────────────────────────────────────────────────────────────────
# KPIs & Ratings (AVG SENTIMENT fix applied)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/kpis")
async def api_kpis(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """
    High-level KPIs:
      - total_reviews (in window)
      - avg_rating
      - avg_sentiment (stored OR rating-proxy; treats 0.0 as NULL)
      - new_reviews (last 7 days ending at end_dt)
    """
    uid = _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    start_dt, end_dt = await _auto_range_last30(company_id, start, end)
    async with get_session() as session:
        date_col = _date_col()
        avg_sent_expr = func.avg(
            func.coalesce(func.nullif(Review.sentiment_score, 0.0), _rating_sent_fallback())
        )
        stmt = (
            select(
                func.count(Review.id),
                func.avg(Review.rating),
                avg_sent_expr,
            )
            .where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
        )
        total, avg_rating, avg_sent = (await session.execute(stmt)).first() or (0, None, None)
        # New reviews (last NEW_REVIEW_DAYS up to end_dt)
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
async def api_ratings_distribution(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Histogram of rating 1..5 within window."""
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    start_dt, end_dt = await _auto_range_last30(company_id, start, end)
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
# 1) Overall Sentiment Share (Pie/Donut)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/sentiment/share")
async def api_sentiment_share(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Counts of positive / neutral / negative (uses rating fallback; treats 0.0 as NULL)."""
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    s, e = await _auto_range_last30(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        s_expr, pos, neu, neg, total = _sentiment_bucket_expr()
        row = (await session.execute(
            select(pos.label("pos"), neu.label("neu"), neg.label("neg"), total.label("total"))
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
        )).first()
    if not row:
        return {"counts": {"positive": 0, "neutral": 0, "negative": 0}, "total": 0, "window": {"start": str(s), "end": str(e)}}
    return {
        "counts": {"positive": int(row.pos or 0), "neutral": int(row.neu or 0), "negative": int(row.neg or 0)},
        "total": int(row.total or 0),
        "window": {"start": str(s), "end": str(e)}
    }


# ──────────────────────────────────────────────────────────────────────────────
# Trends (daily series)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/series/reviews")
async def api_series_reviews(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Daily review volume."""
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    start_dt, end_dt = await _auto_range_last30(company_id, start, end)
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
async def api_series_ratings(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Daily average rating."""
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    start_dt, end_dt = await _auto_range_last30(company_id, start, end)
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
async def api_sentiment_series(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Daily average sentiment score (stored or rating-derived; treats 0.0 as NULL)."""
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    start_dt, end_dt = await _auto_range_last30(company_id, start, end)
    async with get_session() as session:
        date_col = _date_col()
        avg_sent_expr = func.avg(
            func.coalesce(func.nullif(Review.sentiment_score, 0.0), _rating_sent_fallback())
        )
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
async def api_series_overview(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Return all three series in one call."""
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    vol = await api_series_reviews(request, company_id, start, end)
    rat = await api_series_ratings(request, company_id, start, end)
    sen = await api_sentiment_series(request, company_id, start, end)
    return {"volume": vol["series"], "rating": rat["series"], "sentiment": sen["series"], "window": vol["window"]}


# ──────────────────────────────────────────────────────────────────────────────
# 3) Aspect-Based Sentiment (stacked bar data)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/aspects/sentiment")
async def api_aspects_sentiment(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """
    Keyword-based aspect sentiment: Service, Product Quality, Pricing, Delivery.
    Buckets per aspect: positive / neutral / negative + avg sentiment.
    (Uses Negation Logic inside _safe_sentiment for text-derived scores.)
    """
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    s, e = await _auto_range_last30(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        rows = (await session.execute(
            select(Review.text, Review.sentiment_score, Review.rating, Review.google_review_time)
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
            .order_by(desc(Review.google_review_time))
            .limit(20000)
        )).all()
    buckets: Dict[str, Dict[str, int]] = {a: {"positive": 0, "neutral": 0, "negative": 0} for a in _ASPECT_LEX}
    sums: Dict[str, float] = {a: 0.0 for a in _ASPECT_LEX}
    counts: Dict[str, int] = {a: 0 for a in _ASPECT_LEX}
    for text, ss, rating, _ts in rows:
        t = (text or "").lower()
        if not t.strip():
            continue
        score = float(ss) if (ss is not None and abs(float(ss)) >= 1e-9) else _safe_sentiment(text or "", rating)
        label = _label_from_score(score)
        for aspect, kws in _ASPECT_LEX.items():
            if any(kw in t for kw in kws):
                buckets[aspect][label] += 1
                sums[aspect] += score
                counts[aspect] += 1
    result = []
    for aspect in _ASPECT_LEX.keys():
        n = counts[aspect]
        avg = (sums[aspect] / n) if n else 0.0
        result.append({
            "aspect": aspect,
            "positive": buckets[aspect]["positive"],
            "neutral": buckets[aspect]["neutral"],
            "negative": buckets[aspect]["negative"],
            "avg_sentiment": round(avg, 3),
            "n": n,
        })
    return {"window": {"start": str(s), "end": str(e)}, "aspects": result}


# ───────── UPDATED (defensive): numeric aspects average ─────────
@router.get("/api/aspects/avg")
async def api_aspects_average(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """
    Departmental numeric aspects average values.
    Defensive: if any aspect column doesn't exist on Review, returns 0.0 for it.
    Response includes aspects, ranked list, strengths/weaknesses, global average, and window.
    """
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    start_dt, end_dt = await _auto_range_last30(company_id, start, end)
    async with get_session() as session:
        date_col = _date_col()
        aspect_map = {
            "rooms": "aspect_rooms",
            "staff": "aspect_staff",
            "cleanliness": "aspect_cleanliness",
            "value": "aspect_value",
            "location": "aspect_location",
            "food": "aspect_food",
        }
        projections = []
        for public_key, attr_name in aspect_map.items():
            if hasattr(Review, attr_name):
                projections.append(func.avg(getattr(Review, attr_name)).label(public_key))
            else:
                projections.append(literal(0.0).label(public_key))
        stmt = (
            select(*projections)
            .where(and_(Review.company_id == company_id, date_col >= start_dt, date_col <= end_dt))
        )
        try:
            row = (await session.execute(stmt)).one_or_none()
        except Exception:
            row = None
        aspects = {k: 0.0 for k in aspect_map.keys()}
        if row:
            m = row._mapping
            for k in aspects.keys():
                v = m.get(k)
                aspects[k] = float(v) if v is not None else 0.0
        positive_vals = [v for v in aspects.values() if v > 0]
        global_avg = (sum(positive_vals) / len(positive_vals)) if positive_vals else 0.0
        ranked = sorted(aspects.items(), key=lambda kv: -kv[1])
        strengths = sorted(
            [k for k, v in aspects.items() if v >= max(global_avg, 0.6)],
            key=lambda k: -aspects[k]
        )
        weaknesses = sorted(
            [k for k, v in aspects.items() if 0 < v < max(global_avg, 0.6)],
            key=lambda k: aspects[k]
        )
        return {
            "aspects": aspects,
            "ranked": ranked,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "global_avg": round(global_avg, 3),
            "window": {"start": str(start_dt), "end": str(end_dt)}
        }


# ──────────────────────────────────────────────────────────────────────────────
# 4) Trend Over Time (week/month/day)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/trends")
async def api_trends(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None, freq: str = Query("week", regex="^(day|week|month)$")):
    """Average sentiment & rating per period (day|week|month)."""
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    s, e = await _auto_range_last30(company_id, start, end)
    bucket = "day" if freq == "day" else ("week" if freq == "week" else "month")
    async with get_session() as session:
        ts = _ts_col()
        period = func.date_trunc(bucket, ts).label("period")
        sent_expr = func.avg(func.coalesce(func.nullif(Review.sentiment_score, 0.0), _rating_sent_fallback())).label("avg_sentiment")
        rating_expr = func.avg(Review.rating).label("avg_rating")
        stmt = (
            select(period, sent_expr, rating_expr, func.count(Review.id).label("n"))
            .where(and_(Review.company_id == company_id, ts >= s, ts <= datetime.combine(e, datetime.max.time())))
            .group_by(period)
            .order_by(period)
        )
        rows = (await session.execute(stmt)).all()
    series = [{
        "period": r.period.date().isoformat() if isinstance(r.period, datetime) else str(r.period),
        "avg_sentiment": round(float(r.avg_sentiment or 0.0), 3),
        "avg_rating": round(float(r.avg_rating or 0.0), 3),
        "count": int(r.n or 0),
    } for r in rows]
    return {"freq": bucket, "series": series, "window": {"start": str(s), "end": str(e)}}


# ──────────────────────────────────────────────────────────────────────────────
# 5) Review Volume vs Sentiment (dual-axis)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/volume-vs-sentiment")
async def api_volume_vs_sentiment(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None, freq: str = Query("week", regex="^(day|week|month)$")):
    """Bucketed review count and avg sentiment per period for dual-axis chart."""
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    s, e = await _auto_range_last30(company_id, start, end)
    async with get_session() as session:
        ts = _ts_col()
        period = func.date_trunc(freq, ts).label("period")
        avg_sent = func.avg(func.coalesce(func.nullif(Review.sentiment_score, 0.0), _rating_sent_fallback())).label("avg_sentiment")
        cnt = func.count(Review.id).label("count")
        stmt = (
            select(period, avg_sent, cnt)
            .where(and_(Review.company_id == company_id, ts >= s, ts <= datetime.combine(e, datetime.max.time())))
            .group_by(period)
            .order_by(period)
        )
        rows = (await session.execute(stmt)).all()
    return {
        "freq": freq,
        "series": [{
            "period": r.period.date().isoformat() if isinstance(r.period, datetime) else str(r.period),
            "avg_sentiment": round(float(r.avg_sentiment or 0.0), 3),
            "count": int(r.count or 0)
        } for r in rows],
        "window": {"start": str(s), "end": str(e)}
    }


# ──────────────────────────────────────────────────────────────────────────────
# 6) Rating vs Sentiment Correlation (scatter)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/correlation/rating-sentiment")
async def api_correlation_rating_sentiment(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None, limit: int = Query(5000, ge=100, le=50000)):
    """Scatter points: (rating, sentiment, date). Uses rating-proxy when stored sentiment is missing/0."""
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    s, e = await _auto_range_last30(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        rows = (await session.execute(
            select(Review.text, Review.sentiment_score, Review.rating, Review.google_review_time)
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
            .order_by(desc(Review.google_review_time))
            .limit(5000 if limit is None else limit)
        )).all()
    items = []
    for text, ss, rating, ts in rows:
        if rating is None and (ss is None or abs(float(ss)) < 1e-9) and not text:
            continue
        # Use safe sentiment with negation for points
        score = float(ss) if (ss is not None and abs(float(ss)) >= 1e-9) else _safe_sentiment(text or "", rating)
        items.append({
            "rating": float(rating) if rating is not None else None,
            "sentiment": round(float(score), 3),
            "date": ts.strftime("%Y-%m-%d") if isinstance(ts, datetime) else (str(ts) if ts else "")
        })
    return {"points": items, "window": {"start": str(s), "end": str(e)}}


# ──────────────────────────────────────────────────────────────────────────────
# Operational Overview + Alerts
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/operational/overview")
async def api_operational_overview(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None, limit_urgent: int = Query(10, ge=1, le=50)):
    """Operational overview with urgent issues."""
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    start_dt, end_dt = await _auto_range_last30(company_id, start, end)
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
            # Recompute sentiment with negation-aware safe sentiment
            s_val = float(r.sentiment_score) if (r.sentiment_score is not None and abs(float(r.sentiment_score)) >= 1e-9) else _safe_sentiment(text, r.rating)
            s_label = _sentiment_label(s_val)
            has_urgent_kw = any(term in text.lower() for term in _URGENT_TERMS)
            is_urgent = (
                (r.rating is not None and r.rating <= 2) or
                (s_val <= -0.5) or
                (has_urgent_kw)
            )
            if is_urgent:
                urgent_items.append({
                    "review_id": r.id,
                    "author_name": r.author_name or "Anonymous",
                    "rating": int(r.rating or 0),  # defensive for front-end '★'.repeat()
                    "sentiment_score": round(float(s_val or 0.0), 3),
                    "sentiment_label": s_label,
                    "review_time": r.google_review_time.strftime("%Y-%m-%d") if r.google_review_time else "",
                    "text": text[:1200],
                    "profile_photo_url": r.profile_photo_url or "",
                    "urgent_reason": {
                        "low_rating": bool(r.rating is not None and r.rating <= 2),
                        "very_negative_sentiment": bool(s_val <= -0.5),
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


@router.get("/api/alerts")
async def api_alerts(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    """Trend-based alerts using two-window comparisons (last7 vs prev7)."""
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    start_dt, end_dt = await _auto_range_last30(company_id, start, end)
    last7_start = end_dt - timedelta(days=NEW_REVIEW_DAYS - 1)
    prev7_end = last7_start - timedelta(days=1)
    prev7_start = prev7_end - timedelta(days=NEW_REVIEW_DAYS - 1)
    kpis = await api_kpis(request, company_id, start, end)
    ops = await api_operational_overview(request, company_id, start, end, limit_urgent=5)
    vol = await api_series_reviews(request, company_id, start, end)
    vol_map = {s["date"]: s["value"] for s in vol["series"]}
    def _sum_in(a: date, b: date) -> int:
        return sum(vol_map.get(str(a + timedelta(days=i)), 0) for i in range((b - a).days + 1))
    last7 = _sum_in(last7_start, end_dt)
    prev7 = _sum_in(prev7_start, prev7_end)
    alerts = []
    if prev7 >= 8 and last7 <= prev7 * 0.6:
        pct = round(100 - (last7 / max(prev7, 1)) * 100)
        alerts.append({"type": "volume_drop", "severity": "high", "message": f"Review volume down {pct}% vs prior week."})
    rat_series = await api_series_ratings(request, company_id, start, end)
    sen_series = await api_sentiment_series(request, company_id, start, end)
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
# 7) Keywords & 8) AI Summaries (v2)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/v2/sentiment/summary")
async def sentiment_summary_v2(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    s, e = await _auto_range_last30(company_id, start, end)
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
        if ss is None or abs(float(ss)) < 1e-9:
            score = _safe_sentiment(text or "", rating)
            fallback += 1
        else:
            score = float(ss)
            stored += 1
        vals.append(score)
        if score >= 0.35: counts["positive"] += 1
        elif score <= -0.25: counts["negative"] += 1
        else: counts["neutral"] += 1
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
async def keywords_v2(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None, limit: int = Query(20, ge=5, le=50)):
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    s, e = await _auto_range_last30(company_id, start, end)
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
        return {"window": {"start": str(s), "end": str(e)}, "positive": [], "negative": [], "emerging": [], "bigrams": []}
    kw = _keyword_attribution(docs, (l7s, e), (p7s, p7e), top_n=limit)
    bigs = _top_bigrams_docs([d[0] for d in docs], top_n=limit)
    def _cast(items: List[KeywordScore]):
        return [{"term": x.term, "freq": x.freq, "avg_sent": round(x.avg_sent, 3), "contribution": round(x.contribution, 3), "delta": x.delta} for x in items]
    return {
        "window": {"start": str(s), "end": str(e)},
        "positive": _cast(kw["positive"]),
        "negative": _cast(kw["negative"]),
        "emerging": _cast(kw["emerging"]),
     "bigrams": [{"term": t, "freq": f} for (t, f) in bigrams],
