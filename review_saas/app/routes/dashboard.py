# filename: app/routes/dashboard.py
from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import Date, Integer, and_, case, cast, desc, func, literal, select
from starlette.templating import Jinja2Templates

from app.core.db import get_session
from app.core.models import Company, Review
from app.routes.companies import _require_user

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.dashboard")

# ──────────────────────────────────────────────────────────────────────────────
# Constants & Helpers
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_DAYS = 30
NEW_REVIEW_DAYS = 7

# Rating → sentiment proxy fallback
_RATING_PROXY = {5: 0.8, 4: 0.4, 3: 0.0, 2: -0.4, 1: -0.8}

# Stopwords & lexicons
_STOPWORDS = {
    "the", "and", "to", "a", "an", "in", "is", "it", "of", "for", "on", "was", "with", "at",
    "this", "that", "by", "be", "from", "as", "are", "were", "or", "we", "you", "they", "our",
    "your", "their", "but", "so", "if", "too", "very", "can", "could", "would", "will",
    "has", "have", "had", "do", "did", "does", "just", "also", "than", "then", "there", "here",
    "about", "into", "out", "over", "under", "between", "after", "before", "during", "more", "most",
    "less", "least", "again", "ever", "never", "always", "some", "any", "much", "many", "few", "lot", "lots"
}
_NEGATORS = {"not", "never", "no", "hardly", "barely", "scarcely", "without", "lack", "lacking"}
_TOKEN_RE = re.compile(r"[a-zA-Z]+")

_LEX_POS = {
    "great": 4, "excellent": 5, "good": 3, "friendly": 3, "clean": 2, "amazing": 4, "love": 4, "nice": 2,
    "comfortable": 3, "helpful": 3, "fast": 2, "quick": 2, "tasty": 3, "spacious": 2, "professional": 3,
    "responsive": 3, "polite": 2, "courteous": 2, "beautiful": 3, "quiet": 2, "safe": 2, "affordable": 2,
    "fair": 2, "recommend": 3, "recommended": 3, "awesome": 4, "perfect": 4, "best": 4, "delicious": 4,
    "fresh": 2, "warm": 1, "welcoming": 2, "cleanliness": 3, "hygienic": 3
}
_LEX_NEG = {
    "bad": -3, "poor": -3, "worst": -5, "slow": -2, "dirty": -3, "rude": -4, "problem": -2, "issue": -2,
    "disappointed": -3, "expensive": -2, "noisy": -2, "crowded": -2, "delay": -2, "delayed": -2, "broken": -3,
    "smelly": -3, "cold": -1, "hot": -1, "late": -2, "unprofessional": -4, "unhelpful": -3, "refund": -3,
    "fraud": -5, "scam": -5, "unsafe": -4, "hygiene": -2, "lawsuit": -4, "legal": -2, "threat": -4, "hazard": -4,
    "poison": -5, "sick": -3, "expired": -3, "fire": -3, "electrical": -2, "incompetent": -4, "overpriced": -3
}
_LEXICON = {**_LEX_POS, **_LEX_NEG}

# Aspect keyword dictionaries (matches frontend "Service, Product, Pricing, Delivery")
_ASPECT_LEX = {
    "Service": {"service", "staff", "waiter", "host", "attendant", "attentive", "rude", "polite", "friendly", "unprofessional", "helpful"},
    "Product Quality": {"quality", "taste", "fresh", "stale", "clean", "hygiene", "delicious", "burnt", "undercooked", "spoiled"},
    "Pricing": {"price", "pricing", "expensive", "cheap", "affordable", "overpriced", "value", "cost"},
    "Delivery": {"delivery", "deliver", "delivered", "takeaway", "pickup", "late", "delay", "on time", "fast", "quick"},
}

# Terms that flag urgent issues
_URGENT_TERMS = {
    "refund", "fraud", "scam", "unsafe", "health", "hygiene", "lawsuit", "legal", "threat",
    "hazard", "poison", "sick", "food poisoning", "expired", "broken glass", "fire", "electrical"
}


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _range_or_default(start: Optional[str], end: Optional[str], default_days: int = DEFAULT_DAYS) -> Tuple[date, date]:
    today = date.today()
    e = _parse_date(end) or today
    s = _parse_date(start) or (e - timedelta(days=default_days - 1))
    if s > e:
        s, e = e, s
    return s, e


async def _auto_range_last30(company_id: int, start: Optional[str], end: Optional[str]) -> Tuple[date, date]:
    # keep simple for now; hook to change per company if needed
    return _range_or_default(start, end, DEFAULT_DAYS)


def _date_col() -> Any:
    """DATE expression for filtering windows; prefers google_review_time then created_at."""
    base = getattr(Review, "google_review_time", None)
    created = getattr(Review, "created_at", None)
    if base is not None and created is not None:
        return cast(func.coalesce(Review.google_review_time, Review.created_at), Date)
    return cast(Review.google_review_time, Date)


def _ts_col() -> Any:
    """TIMESTAMP expression for grouping/bucketing."""
    base = getattr(Review, "google_review_time", None)
    created = getattr(Review, "created_at", None)
    if base is not None and created is not None:
        return func.coalesce(Review.google_review_time, Review.created_at)
    return Review.google_review_time


def _rating_sent_fallback():
    """Fallback sentiment proxy from rating (works if rating stored as text or int)."""
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
    Returns expressions:
      s_expr (final sentiment), pos, neu, neg, total
    Semantics: treat 0.0 as missing, fallback to rating-based proxy.
    """
    s_expr = func.coalesce(func.nullif(Review.sentiment_score, 0.0), _rating_sent_fallback())
    pos = func.sum(case((s_expr >= 0.35, 1), else_=0))
    neg = func.sum(case((s_expr <= -0.25, 1), else_=0))
    total = func.count(Review.id)
    neu = total - pos - neg
    return s_expr, pos, neu, neg, total


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    toks = [t.lower() for t in _TOKEN_RE.findall(text)]
    out: List[str] = []
    for t in toks:
        if len(t) <= 2:
            continue
        if t in _NEGATORS:  # keep negators
            out.append(t)
            continue
        if t in _STOPWORDS:
            continue
        out.append(t)
    return out


def _bigrams(tokens: List[str]) -> List[str]:
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]


def _clamp(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


def _lexicon_sentiment_with_negation(tokens: List[str]) -> float:
    """
    Sum lexicon scores; flip positive tokens if a negator appears in a small lookback window.
    """
    if not tokens:
        return 0.0
    score = 0.0
    n = len(tokens)
    for i, t in enumerate(tokens):
        base = _LEXICON.get(t, 0)
        if base > 0:
            j0 = max(0, i - 3)
            if any(tokens[j] in _NEGATORS for j in range(j0, i)):
                base = -abs(base)
        score += base
    norm = score / max(1.0, math.sqrt(n))
    return _clamp(norm / 5.0, -1.0, 1.0)


def _safe_sentiment(text: str, rating: Optional[int] = None, fallback_weight: float = 0.35) -> float:
    tokens = _tokenize(text or "")
    lex = _lexicon_sentiment_with_negation(tokens)
    if rating is None:
        return lex
    proxy = _RATING_PROXY.get(int(rating), 0.0)
    return _clamp((1 - fallback_weight) * lex + fallback_weight * proxy, -1.0, 1.0)


def _label_from_score(score: float) -> str:
    if score >= 0.35:
        return "positive"
    if score <= -0.25:
        return "negative"
    return "neutral"


@dataclass
class KeywordScore:
    term: str
    freq: int
    avg_sent: float
    contribution: float
    delta: int = 0


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
        s = float(sent) if (sent is not None and abs(float(sent)) >= 1e-9) else _safe_sentiment(text, rating)
        toks = _tokenize(text)
        for t in toks:
            token_counts[t] += 1
            token_sent_sum[t] += s
            token_times.append((t, ts))

    scores: List[KeywordScore] = []
    for term, freq in token_counts.items():
        avg = token_sent_sum[term] / max(1, freq)
        scores.append(KeywordScore(term=term, freq=int(freq), avg_sent=float(avg), contribution=float(avg * freq)))

    l7s, l7e = last7
    p7s, p7e = prev7
    last7_c: Counter = Counter()
    prev7_c: Counter = Counter()
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
        s.delta = int(growth.get(s.term, 0))

    positive = sorted([s for s in scores if s.avg_sent > 0], key=lambda x: (x.contribution, x.freq), reverse=True)[:top_n]
    negative = sorted([s for s in scores if s.avg_sent < 0], key=lambda x: (abs(x.contribution), x.freq), reverse=True)[:top_n]
    emerging = sorted([s for s in scores if s.delta > 0 and s.freq >= 2], key=lambda x: (x.delta, x.freq), reverse=True)[:top_n]
    return {"positive": positive, "negative": negative, "emerging": emerging}


def _top_bigrams_docs(docs: Iterable[str], top_n: int = 20) -> List[Tuple[str, int]]:
    counter: Counter = Counter()
    for text in docs:
        toks = _tokenize(text or "")
        for bg in _bigrams(toks):
            w1, w2 = bg.split()
            if w1 in _STOPWORDS or w2 in _STOPWORDS:
                continue
            counter[bg] += 1
    return counter.most_common(top_n)


# ──────────────────────────────────────────────────────────────────────────────
# Page route
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, company_id: Optional[int] = Query(None)):
    _require_user(request)  # raises 401 if not authenticated
    async with get_session() as session:
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
# KPIs
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/kpis")
async def api_kpis(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")

    start_dt, end_dt = await _auto_range_last30(company_id, start, end)

    async with get_session() as session:
        dc = _date_col()
        avg_sent_expr = func.avg(func.coalesce(func.nullif(Review.sentiment_score, 0.0), _rating_sent_fallback()))
        stmt = (
            select(func.count(Review.id), func.avg(Review.rating), avg_sent_expr)
            .where(and_(Review.company_id == company_id, dc >= start_dt, dc <= end_dt))
        )
        total, avg_rating, avg_sent = (await session.execute(stmt)).first() or (0, 0.0, 0.0)

        # new reviews last 7d ending at end_dt
        new_start = end_dt - timedelta(days=NEW_REVIEW_DAYS - 1)
        q_new = await session.execute(
            select(func.count(Review.id)).where(and_(Review.company_id == company_id, dc >= new_start, dc <= end_dt))
        )
        new_reviews = int(q_new.scalar() or 0)

    return {
        "window": {"start": str(start_dt), "end": str(end_dt)},
        "total_reviews": int(total or 0),
        "avg_rating": round(float(avg_rating or 0.0), 2),
        "avg_sentiment": round(float(avg_sent or 0.0), 3),
        "new_reviews": new_reviews,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Series (volume / ratings / sentiment + overview)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/series/reviews")
async def api_series_reviews(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")

    s, e = await _auto_range_last30(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        d_alias = dc.label("date")
        rows = (await session.execute(
            select(d_alias, func.count(Review.id).label("value"))
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
            .group_by(d_alias)
            .order_by(d_alias)
        )).all()
    series = [{"date": str(r.date), "value": int(r.value or 0)} for r in rows]
    return {"series": series, "window": {"start": str(s), "end": str(e)}}


@router.get("/api/series/ratings")
async def api_series_ratings(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")

    s, e = await _auto_range_last30(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        d_alias = dc.label("date")
        rows = (await session.execute(
            select(d_alias, func.avg(Review.rating).label("value"))
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
            .group_by(d_alias)
            .order_by(d_alias)
        )).all()
    series = [{"date": str(r.date), "value": round(float(r.value or 0.0), 3)} for r in rows]
    return {"series": series, "window": {"start": str(s), "end": str(e)}}


@router.get("/api/sentiment/series")
async def api_sentiment_series(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")

    s, e = await _auto_range_last30(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        d_alias = dc.label("date")
        avg_sent_expr = func.avg(func.coalesce(func.nullif(Review.sentiment_score, 0.0), _rating_sent_fallback()))
        rows = (await session.execute(
            select(d_alias, avg_sent_expr.label("value"))
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
            .group_by(d_alias)
            .order_by(d_alias)
        )).all()
    series = [{"date": str(r.date), "value": round(float(r.value or 0.0), 3)} for r in rows]
    return {"series": series, "window": {"start": str(s), "end": str(e)}}


@router.get("/api/series/overview")
async def api_series_overview(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
    vol = await api_series_reviews(request, company_id, start, end)
    rat = await api_series_ratings(request, company_id, start, end)
    sen = await api_sentiment_series(request, company_id, start, end)
    return {
        "volume": vol["series"],
        "rating": rat["series"],
        "sentiment": sen["series"],
        "window": vol["window"],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Ratings distribution & sentiment share
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/ratings/distribution")
async def api_ratings_distribution(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")

    s, e = await _auto_range_last30(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        rows = (await session.execute(
            select(Review.rating, func.count(Review.id))
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
            .group_by(Review.rating)
        )).all()

    dist = {i: 0 for i in range(1, 6)}
    for rating, cnt in rows:
        if rating in dist:
            dist[int(rating)] = int(cnt or 0)
    return {"distribution": dist, "window": {"start": str(s), "end": str(e)}}


@router.get("/api/sentiment/share")
async def api_sentiment_share(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
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
        "window": {"start": str(s), "end": str(e)},
    }


# ──────────────────────────────────────────────────────────────────────────────
# Aspects (keyword-based)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/aspects/sentiment")
async def api_aspects_sentiment(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
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


# ──────────────────────────────────────────────────────────────────────────────
# Operational overview & alerts
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/operational/overview")
async def api_operational_overview(
    request: Request,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit_urgent: int = Query(10, ge=1, le=50),
):
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")

    s, e = await _auto_range_last30(company_id, start, end)
    async with get_session() as session:
        dc = _date_col()
        total = (await session.execute(
            select(func.count(Review.id)).where(and_(Review.company_id == company_id, dc >= s, dc <= e))
        )).scalar() or 0

        complaints = (await session.execute(
            select(func.count(Review.id)).where(and_(Review.company_id == company_id, dc >= s, dc <= e, Review.is_complaint == True))  # noqa: E712
        )).scalar() or 0

        praise = (await session.execute(
            select(func.count(Review.id)).where(and_(Review.company_id == company_id, dc >= s, dc <= e, Review.is_praise == True))  # noqa: E712
        )).scalar() or 0

        complaint_rate = round((complaints / total) * 100, 1) if total else 0.0
        praise_rate = round((praise / total) * 100, 1) if total else 0.0

        urgent_stmt = (
            select(
                Review.id, Review.author_name, Review.rating, Review.text,
                Review.sentiment_score, Review.google_review_time, Review.profile_photo_url
            )
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
            .order_by(desc(Review.google_review_time))
            .limit(500)
        )
        urgent_rows = (await session.execute(urgent_stmt)).all()

    urgent_items: List[Dict[str, Any]] = []
    for r in urgent_rows:
        text = r.text or ""
        s_val = float(r.sentiment_score) if (r.sentiment_score is not None and abs(float(r.sentiment_score)) >= 1e-9) else _safe_sentiment(text, r.rating)
        s_label = _label_from_score(s_val)
        has_kw = any(term in text.lower() for term in _URGENT_TERMS)
        is_urgent = ((r.rating is not None and r.rating <= 2) or (s_val <= -0.5) or has_kw)
        if is_urgent:
            urgent_items.append({
                "review_id": r.id,
                "author_name": r.author_name or "Anonymous",
                "rating": int(r.rating or 0),
                "sentiment_score": round(float(s_val or 0.0), 3),
                "sentiment_label": s_label,
                "review_time": r.google_review_time.strftime("%Y-%m-%d") if isinstance(r.google_review_time, datetime) else (str(r.google_review_time) if r.google_review_time else ""),
                "text": text[:1200],
                "profile_photo_url": r.profile_photo_url or "",
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
        "window": {"start": str(s), "end": str(e)},
    }


@router.get("/api/alerts")
async def api_alerts(request: Request, company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    _require_user(request)
    async with get_session() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")

    s, e = await _auto_range_last30(company_id, start, end)

    # Build series to compare last7 vs prev7
    last7_start = e - timedelta(days=NEW_REVIEW_DAYS - 1)
    prev7_end = last7_start - timedelta(days=1)
    prev7_start = prev7_end - timedelta(days=NEW_REVIEW_DAYS - 1)

    vol = await api_series_reviews(request, company_id, start, end)
    vol_map = {s["date"]: s["value"] for s in vol["series"]}

    def _sum_in(a: date, b: date) -> int:
        days = (b - a).days + 1
        return sum(vol_map.get(str(a + timedelta(days=i)), 0) for i in range(days))

    last7 = _sum_in(last7_start, e)
    prev7 = _sum_in(prev7_start, prev7_end)

    rat_series = await api_series_ratings(request, company_id, start, end)
    sen_series = await api_sentiment_series(request, company_id, start, end)

    def _avg_in(series: List[Dict[str, Any]], a: date, b: date) -> float:
        vals = [s["value"] for s in series if a <= datetime.strptime(s["date"], "%Y-%m-%d").date() <= b]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    rating_last7 = _avg_in(rat_series["series"], last7_start, e)
    rating_prev7 = _avg_in(rat_series["series"], prev7_start, prev7_end)
    sentiment_last7 = _avg_in(sen_series["series"], last7_start, e)
    sentiment_prev7 = _avg_in(sen_series["series"], prev7_start, prev7_end)

    alerts: List[Dict[str, Any]] = []
    if prev7 >= 8 and last7 <= prev7 * 0.6:
        pct = round(100 - (last7 / max(prev7, 1)) * 100)
        alerts.append({"type": "volume_drop", "severity": "high", "message": f"Review volume down {pct}% vs prior week."})
    if rating_prev7 > 0 and rating_last7 <= rating_prev7 - 0.3:
        alerts.append({"type": "rating_dip", "severity": "medium", "message": f"Avg rating dropped {round(rating_prev7 - rating_last7, 2)} vs prior week."})
    if sentiment_prev7 > 0 and sentiment_last7 <= sentiment_prev7 - 0.1:
        alerts.append({"type": "sentiment_dip", "severity": "medium", "message": f"Avg sentiment dropped {round(sentiment_prev7 - sentiment_last7, 3)} vs prior week."})

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
        "window": {"start": str(s), "end": str(e)},
    }


# ──────────────────────────────────────────────────────────────────────────────
# v2: compact summary + keywords (used by frontend Executive Summary/Keywords)
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
        s_expr, pos, neu, neg, total = _sentiment_bucket_expr()
        avg_sent = func.avg(func.coalesce(func.nullif(Review.sentiment_score, 0.0), _rating_sent_fallback()))
        avg_rating = func.avg(Review.rating)
        row = (await session.execute(
            select(pos.label("pos"), neu.label("neu"), neg.label("neg"), total.label("total"),
                   avg_sent.label("avg_sent"), avg_rating.label("avg_rating"))
            .where(and_(Review.company_id == company_id, dc >= s, dc <= e))
        )).first()

    if not row:
        return {
            "window": {"start": str(s), "end": str(e)},
            "total": 0,
            "avg_rating": 0.0,
            "avg_sentiment": 0.0,
            "share": {"positive": 0, "neutral": 0, "negative": 0},
        }

    return {
        "window": {"start": str(s), "end": str(e)},
        "total": int(row.total or 0),
        "avg_rating": round(float(row.avg_rating or 0.0), 3),
        "avg_sentiment": round(float(row.avg_sent or 0.0), 3),
        "share": {
            "positive": int(row.pos or 0),
            "neutral": int(row.neu or 0),
            "negative": int(row.neg or 0),
        },
    }


@router.get("/api/v2/keywords")
async def keywords_v2(
    request: Request,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(20, ge=5, le=50),
):
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
        return {
            "window": {"start": str(s), "end": str(e)},
            "positive": [],
            "negative": [],
            "emerging": [],
            "bigrams": [],
        }

    kw = _keyword_attribution(docs, (l7s, e), (p7s, p7e), top_n=limit)
    bigs = _top_bigrams_docs([d[0] for d in docs], top_n=limit)

    def _cast(items: List[KeywordScore]):
        return [
            {
                "term": x.term,
                "freq": x.freq,
                "avg_sent": round(x.avg_sent, 3),
                "contribution": round(x.contribution, 3),
                "delta": x.delta,
            }
            for x in items
        ]

    return {
        "window": {"start": str(s), "end": str(e)},
        "positive": _cast(kw["positive"]),
        "negative": _cast(kw["negative"]),
        "emerging": _cast(kw["emerging"]),
        "bigrams": [{"term": term, "freq": int(freq)} for term, freq in bigs],
    }
