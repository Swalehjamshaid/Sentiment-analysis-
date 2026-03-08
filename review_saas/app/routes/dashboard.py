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
from fastapi.responses import HTMLResponse, Response, JSONResponse
from sqlalchemy import Date, and_, case, cast, desc, func, select, Integer
from starlette.templating import Jinja2Templates

from app.core.db import get_session
from app.core.models import Company, Review
from app.routes.companies import _require_user

router = APIRouter(tags=["dashboard"])  # legacy + v2 endpoints live here as well
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.dashboard")

# ──────────────────────────────────────────────────────────────────────────────
# Utilities & Global Attributes
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_DAYS = 30
NEW_REVIEW_DAYS = 7

# Rating → sentiment proxy (consistent for every site)
_RATING_PROXY = {5: 0.8, 4: 0.4, 3: 0.0, 2: -0.4, 1: -0.8}

_STOPWORDS = {
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

_ASPECT_LEX = {
    "Service": {"service", "staff", "waiter", "host", "attendant", "attentive", "rude", "polite", "friendly", "unprofessional", "helpful"},
    "Product Quality": {"quality", "taste", "fresh", "stale", "clean", "hygiene", "delicious", "burnt", "undercooked", "spoiled"},
    "Pricing": {"price", "pricing", "expensive", "cheap", "affordable", "overpriced", "value", "cost"},
    "Delivery": {"delivery", "deliver", "delivered", "takeaway", "pickup", "late", "delay", "on time", "fast", "quick"},
}

_ASPECT_TREND_CANON = {
    "Service": _ASPECT_LEX["Service"],
    "Product": _ASPECT_LEX["Product Quality"],
    "Pricing": _ASPECT_LEX["Pricing"],
    "Delivery": _ASPECT_LEX["Delivery"],
}

# --- Basic parsing helpers ----------------------------------------------------
def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str: return None
    try: return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception: return None

def _range_or_default(start: Optional[str], end: Optional[str], default_days: int = DEFAULT_DAYS) -> Tuple[date, date]:
    today = date.today()
    end_dt = _parse_date(end) or today
    start_dt = _parse_date(start) or (end_dt - timedelta(days=default_days - 1))
    if start_dt > end_dt: start_dt, end_dt = end_dt, start_dt
    return start_dt, end_dt

def _date_col() -> any:
    base = getattr(Review, "google_review_time", None)
    created = getattr(Review, "created_at", None)
    if base is not None and created is not None:
        return cast(func.coalesce(Review.google_review_time, Review.created_at), Date)
    return cast(Review.google_review_time, Date)

def _ts_col() -> any:
    base = getattr(Review, "google_review_time", None)
    created = getattr(Review, "created_at", None)
    if base is not None and created is not None:
        return func.coalesce(Review.google_review_time, Review.created_at)
    return Review.google_review_time

async def _min_date_for_company(company_id: int) -> Optional[date]:
    async with get_session() as session:
        dc = _date_col()
        q = await session.execute(select(func.min(dc)).where(Review.company_id == company_id))
        d = q.scalar()
    if isinstance(d, datetime): return d.date()
    return d

async def _auto_range_full_history(company_id: int, start: Optional[str], end: Optional[str]) -> Tuple[date, date]:
    """If UI does not pass dates, use full history starting from earliest review found."""
    if start or end: return _range_or_default(start, end)
    mn = await _min_date_for_company(company_id)
    today = date.today()
    if mn is None: return _range_or_default(None, None)
    return (mn if mn <= today else today), today

def _rating_sent_fallback():
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
    s_expr = func.coalesce(func.nullif(Review.sentiment_score, 0.0), _rating_sent_fallback())
    pos = func.sum(case((s_expr >= 0.35, 1), else_=0))
    neg = func.sum(case((s_expr <= -0.25, 1), else_=0))
    total = func.count(Review.id)
    neu = total - pos - neg
    return s_expr, pos, neu, neg, total

# ──────────────────────────────────────────────────────────────────────────────
# NLP Intelligence Engine (Negation Aware)
# ──────────────────────────────────────────────────────────────────────────────
TOKEN_RE = re.compile(r"[a-zA-Z]+")
_NEGATORS = {"not", "never", "no", "hardly", "barely", "scarcely", "without", "lack", "lacking"}

@dataclass
class KeywordScore:
    term: str
    freq: int
    avg_sent: float
    contribution: float
    delta: int = 0

_LEX_POS = {k: 4 for k in _POSITIVE_HINTS}
_LEX_NEG = {k: -4 for k in _NEGATIVE_HINTS}
_LEXICON = {**_LEX_POS, **_LEX_NEG}

def _tokenize(text: str) -> List[str]:
    if not text: return []
    toks = [t.lower() for t in TOKEN_RE.findall(text)]
    out = []
    for t in toks:
        if len(t) <= 2 and t not in _NEGATORS: continue
        if t in _STOPWORDS and t not in _NEGATORS: continue
        out.append(t)
    return out

def _lexicon_sentiment_with_negation(tokens: List[str]) -> float:
    if not tokens: return 0.0
    score, n = 0.0, len(tokens)
    for i, t in enumerate(tokens):
        base = _LEXICON.get(t, 0)
        if base > 0:
            j0 = max(0, i - 3)
            if any(tokens[j] in _NEGATORS for j in range(j0, i)):
                base = -abs(base)
        score += base
    norm = score / max(1.0, math.sqrt(n))
    return float(max(-1.0, min(1.0, norm / 5.0)))

def _safe_sentiment(text: str, rating: Optional[int] = None, fallback_weight: float = 0.35) -> float:
    toks = _tokenize(text or "")
    lex = _lexicon_sentiment_with_negation(toks)
    if rating is None: return lex
    rate_proxy = _RATING_PROXY.get(int(rating), 0.0)
    return float(max(-1.0, min(1.0, (1 - fallback_weight) * lex + fallback_weight * rate_proxy)))

def _keyword_attribution(docs, last7, prev7, top_n=20):
    token_counts, token_sent_sum, token_times = Counter(), defaultdict(float), []
    for text, sent, rating, ts in docs:
        if not text: continue
        toks = _tokenize(text)
        s = sent if (sent is not None and abs(float(sent)) >= 1e-9) else _safe_sentiment(text, rating)
        for t in toks:
            token_counts[t] += 1
            token_sent_sum[t] += s
            token_times.append((t, ts))
    scores = []
    for term, freq in token_counts.items():
        avg = (token_sent_sum[term] / max(1, freq))
        scores.append(KeywordScore(term=term, freq=int(freq), avg_sent=float(avg), contribution=float(avg*freq)))
    l7s, l7e, p7s, p7e = last7[0], last7[1], prev7[0], prev7[1]
    last7_c, prev7_c = Counter(), Counter()
    for t, ts in token_times:
        if not ts: continue
        d = ts.date()
        if l7s <= d <= l7e: last7_c[t] += 1
        elif p7s <= d <= p7e: prev7_c[t] += 1
    for s in scores: s.delta = last7_c.get(s.term, 0) - prev7_c.get(s.term, 0)
    return {
        "positive": sorted([s for s in scores if s.avg_sent > 0], key=lambda x: (x.contribution, x.freq), reverse=True)[:top_n],
        "negative": sorted([s for s in scores if s.avg_sent < 0], key=lambda x: (abs(x.contribution), x.freq), reverse=True)[:top_n],
        "emerging": sorted([s for s in scores if s.delta > 0 and s.freq >= 2], key=lambda x: (x.delta, x.freq), reverse=True)[:top_n]
    }

# ──────────────────────────────────────────────────────────────────────────────
# Dashboard + Links
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, company_id: Optional[int] = Query(None)):
    uid = _require_user(request)
    if not uid: return templates.TemplateResponse("login.html", {"request": request, "error": "Session expired."})
    async with get_session() as session:
        companies = (await session.execute(select(Company).order_by(Company.name))).scalars().all()
    active_id = int(company_id) if company_id else (int(companies[0].id) if companies else None)
    api_links = {
        "kpis": "/api/kpis", "ratings_distribution": "/api/ratings/distribution",
        "sentiment_share": "/api/sentiment/share", "series_reviews": "/api/series/reviews",
        "series_ratings": "/api/series/ratings", "series_sentiment": "/api/sentiment/series",
        "trends": "/api/trends", "volume_vs_sentiment": "/api/volume-vs-sentiment",
        "correlation_rating_sentiment": "/api/correlation/rating-sentiment",
        "aspects_sentiment": "/api/aspects/sentiment", "aspects_avg": "/api/aspects/avg",
        "alerts": "/api/alerts", "operational": "/api/operational/overview",
        "reviews_list": "/api/reviews/list", "v2_keywords": "/api/v2/keywords",
        "v2_sentiment_summary": "/api/v2/sentiment/summary", "v2_exec_summary": "/api/v2/ai/executive-summary",
        "v2_recommendations": "/api/v2/ai/recommendations", "v2_summary_png": "/api/v2/charts/summary.png",
        "aspect_trend": "/api/operational/aspect-trend", "alert_email": "/api/alerts/high-severity-email"
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "companies": companies, "active_company_id": active_id, "api_links": api_links
    })

# ──────────────────────────────────────────────────────────────────────────────
# KPIs & Ratings
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/kpis")
async def api_kpis(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    start_dt, end_dt = await _auto_range_full_history(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        avg_sent_expr = func.avg(func.coalesce(func.nullif(Review.sentiment_score, 0.0), _rating_sent_fallback()))
        stmt = select(func.count(Review.id), func.avg(Review.rating), avg_sent_expr).where(
            and_(Review.company_id == company_id, dc >= start_dt, dc <= end_dt)
        )
        total, avg_rating, avg_sent = (await session.execute(stmt)).first() or (0, 0, 0)
        new_start = end_dt - timedelta(days=6)
        q_new = await session.execute(select(func.count(Review.id)).where(
            and_(Review.company_id == company_id, dc >= new_start, dc <= end_dt)
        ))
    return {
        "window": {"start": str(start_dt), "end": str(end_dt)},
        "total_reviews": int(total or 0), "avg_rating": round(float(avg_rating or 0.0), 2),
        "avg_sentiment": round(float(avg_sent or 0.0), 3), "new_reviews": int(q_new.scalar() or 0)
    }

@router.get("/api/ratings/distribution")
async def api_ratings_distribution(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    start_dt, end_dt = await _auto_range_full_history(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        stmt = select(Review.rating, func.count(Review.id)).where(
            and_(Review.company_id == company_id, dc >= start_dt, dc <= end_dt)
        ).group_by(Review.rating)
        res = await session.execute(stmt)
        dist = {i: 0 for i in range(1, 6)}
        for r, c in res.all(): dist[int(r)] = int(c or 0)
    return {"distribution": dist, "window": {"start": str(start_dt), "end": str(end_dt)}}

@router.get("/api/sentiment/share")
async def api_sentiment_share(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    s, e = await _auto_range_full_history(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        s_expr, pos, neu, neg, total = _sentiment_bucket_expr()
        row = (await session.execute(select(pos.label("pos"), neu.label("neu"), neg.label("neg"), total.label("total"))
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e)))).first()
    if not row: return {"counts": {"positive": 0, "neutral": 0, "negative": 0}, "total": 0}
    return {
        "counts": {"positive": int(row.pos or 0), "neutral": int(row.neu or 0), "negative": int(row.neg or 0)},
        "total": int(row.total or 0), "window": {"start": str(s), "end": str(e)}
    }

# ──────────────────────────────────────────────────────────────────────────────
# Series & Trends
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/series/reviews")
async def api_series_reviews(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    start_dt, end_dt = await _auto_range_full_history(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        res = await session.execute(select(dc.label("date"), func.count(Review.id).label("value"))
            .where(and_(Review.company_id == company_id, dc >= start_dt, dc <= end_dt))
            .group_by("date").order_by("date"))
    return {"series": [{"date": str(r.date), "value": int(r.value or 0)} for r in res.all()]}

@router.get("/api/series/ratings")
async def api_series_ratings(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    start_dt, end_dt = await _auto_range_full_history(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        res = await session.execute(select(dc.label("date"), func.avg(Review.rating).label("value"))
            .where(and_(Review.company_id == company_id, dc >= start_dt, dc <= end_dt))
            .group_by("date").order_by("date"))
    return {"series": [{"date": str(r.date), "value": round(float(r.value or 0.0), 3)} for r in res.all()]}

@router.get("/api/sentiment/series")
async def api_sentiment_series(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    start_dt, end_dt = await _auto_range_full_history(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        avg_sent_expr = func.avg(func.coalesce(func.nullif(Review.sentiment_score, 0.0), _rating_sent_fallback()))
        res = await session.execute(select(dc.label("date"), avg_sent_expr.label("value"))
            .where(and_(Review.company_id == company_id, dc >= start_dt, dc <= end_dt))
            .group_by("date").order_by("date"))
    return {"series": [{"date": str(r.date), "value": round(float(r.value or 0.0), 3)} for r in res.all()]}

# ──────────────────────────────────────────────────────────────────────────────
# Aspect Analysis
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/aspects/sentiment")
async def api_aspects_sentiment(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    s, e = await _auto_range_full_history(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        rows = (await session.execute(select(Review.text, Review.sentiment_score, Review.rating)
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e)).limit(20000))).all()
    buckets = {a: {"positive": 0, "neutral": 0, "negative": 0} for a in _ASPECT_LEX}
    sums, counts = {a: 0.0 for a in _ASPECT_LEX}, {a: 0 for a in _ASPECT_LEX}
    for text, ss, rating in rows:
        t = (text or "").lower()
        score = float(ss) if (ss and abs(float(ss)) >= 1e-9) else _safe_sentiment(text, rating)
        label = "positive" if score >= 0.35 else ("negative" if score <= -0.25 else "neutral")
        for aspect, kws in _ASPECT_LEX.items():
            if any(kw in t for kw in kws):
                buckets[aspect][label] += 1
                sums[aspect] += score
                counts[aspect] += 1
    result = [{"aspect": a, "positive": buckets[a]["positive"], "neutral": buckets[a]["neutral"], "negative": buckets[a]["negative"], "avg_sentiment": round(sums[a]/counts[a] if counts[a] else 0, 3)} for a in _ASPECT_LEX]
    return {"aspects": result}

# ──────────────────────────────────────────────────────────────────────────────
# Operational Overview
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/operational/overview")
async def api_operational_overview(company_id: int, start: Optional[str] = None, end: Optional[str] = None, limit_urgent: int = 10):
    start_dt, end_dt = await _auto_range_full_history(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        total = (await session.execute(select(func.count(Review.id)).where(and_(Review.company_id == company_id, dc >= start_dt, dc <= end_dt)))).scalar() or 0
        urgent_rows = (await session.execute(select(Review.id, Review.author_name, Review.rating, Review.text, Review.sentiment_score, Review.google_review_time)
            .where(and_(Review.company_id == company_id, dc >= start_dt, dc <= end_dt))
            .order_by(desc(Review.google_review_time)).limit(500))).all()
    urgent_items = []
    for r in urgent_rows:
        s_val = float(r.sentiment_score) if (r.sentiment_score and abs(float(r.sentiment_score)) >= 1e-9) else _safe_sentiment(r.text, r.rating)
        if (r.rating and r.rating <= 2) or s_val <= -0.5 or any(t in (r.text or "").lower() for t in _URGENT_TERMS):
            urgent_items.append({"review_id": r.id, "author": r.author_name, "rating": r.rating, "sentiment": round(s_val, 3), "text": (r.text or "")[:1200]})
        if len(urgent_items) >= limit_urgent: break
    return {"total_reviews": total, "urgent_issues": urgent_items}

# ──────────────────────────────────────────────────────────────────────────────
# Reviews list (with sorting)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/reviews/list")
async def api_reviews_list(company_id: int, start: Optional[str] = None, end: Optional[str] = None, sort: Optional[str] = Query("newest")):
    start_dt, end_dt = await _auto_range_full_history(company_id, start, end)
    dc = _date_col()
    order = {"oldest": dc.asc(), "highest": Review.rating.desc(), "lowest": Review.rating.asc()}.get(sort, dc.desc())
    async with get_session() as session:
        res = await session.execute(select(Review).where(and_(Review.company_id == company_id, dc >= start_dt, dc <= end_dt)).order_by(order))
        items = res.scalars().all()
    return {"items": [{"author": r.author_name, "rating": r.rating, "text": r.text, "sentiment": round(_safe_sentiment(r.text, r.rating), 3), "time": str(r.google_review_time)} for r in items]}

# ──────────────────────────────────────────────────────────────────────────────
# AI Summary & V2 Endpoints
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/v2/sentiment/summary")
async def sentiment_summary_v2(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    s, e = await _auto_range_full_history(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        rows = (await session.execute(select(Review.text, Review.sentiment_score, Review.rating).where(and_(Review.company_id == company_id, dc >= s, dc <= e)).limit(10000))).all()
    if not rows: return {"avg": 0.0, "total": 0}
    vals = [float(r[1]) if (r[1] and abs(float(r[1])) >= 1e-9) else _safe_sentiment(r[0], r[2]) for r in rows]
    return {"avg": round(sum(vals)/len(vals), 3), "total": len(vals), "window": {"start": str(s), "end": str(e)}}

@router.get("/api/v2/keywords")
async def keywords_v2(company_id: int, start: Optional[str] = None, end: Optional[str] = None, limit: int = 20):
    s, e = await _auto_range_full_history(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        rows = (await session.execute(select(Review.text, Review.sentiment_score, Review.rating, Review.google_review_time).where(and_(Review.company_id == company_id, dc >= s, dc <= e)).limit(10000))).all()
    kw = _keyword_attribution(rows, (e-timedelta(days=6), e), (e-timedelta(days=13), e-timedelta(days=7)), top_n=limit)
    return {"positive": kw["positive"], "negative": kw["negative"], "emerging": kw["emerging"]}

@router.get("/api/v2/ai/executive-summary")
async def executive_summary_v2(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    sent = await sentiment_summary_v2(company_id, start, end)
    return {"summary": f"Average sentiment for the period is {sent['avg']}.", "conclusion": "System Stable"}

@router.get("/api/v2/ai/recommendations")
async def recommendations_v2(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    return {"top_action_items": ["Review staff response times", "Check cleanliness feedback"]}

@router.get("/api/operational/aspect-trend")
async def api_operational_aspect_trend(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    s, e = await _auto_range_full_history(company_id, start, end)
    # Placeholder for trend calculation logic
    return {"metrics": {"Service": {"delta": 0.02}, "Pricing": {"delta": -0.05}}}
