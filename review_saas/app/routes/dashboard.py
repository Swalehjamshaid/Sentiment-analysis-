# filename: app/routes/dashboard.py
from __future__ import annotations

import hmac
import hashlib
import logging
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request, Form, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import Date, Integer, and_, case, cast, desc, func, literal, select, or_
from starlette.templating import Jinja2Templates

from app.core.db import get_session
from app.core.models import Company, Review
from app.routes.companies import _require_user

# Optional AI summary service (best-effort import)
try:  # pragma: no cover - optional dependency
    from app.services.ai_insights import summarize_dashboard as _ai_summarize_dashboard  # type: ignore
except Exception:  # pragma: no cover
    _ai_summarize_dashboard = None  # type: ignore

# Optional Google reviews service references (not called here; kept for compatibility)
try:  # pragma: no cover
    from app.services.google_reviews import ingest_company_reviews, CompanyReviews  # type: ignore
except Exception:  # pragma: no cover
    ingest_company_reviews = None  # type: ignore
    CompanyReviews = None  # type: ignore

# Try to import User if you have it; otherwise ENV fallback login still works.
try:
    from app.core.models import User  # type: ignore
except Exception:  # pragma: no cover
    User = None  # noqa: N816

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.dashboard")

# ──────────────────────────────────────────────────────────────────────────────
# Auth helpers (login flow + safe current_user)
# ──────────────────────────────────────────────────────────────────────────────

def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _verify_password(plain: str, stored_hash: Optional[str]) -> bool:
    """
    Supports:
      - bcrypt ($2x$)
      - sha256 custom: 'sha256$<salt>$<hexdigest>'
      - plain fallback (dev only)
    """
    if stored_hash is None:
        return False
    try:
        if stored_hash.startswith("$2"):  # bcrypt
            try:
                import bcrypt  # type: ignore
            except Exception:
                logger.warning("bcrypt not installed; cannot verify bcrypt hash.")
                return False
            try:
                return bcrypt.checkpw(plain.encode("utf-8"), stored_hash.encode("utf-8"))
            except Exception as e:
                logger.error("bcrypt.checkpw failed: %s", e)
                return False

        if stored_hash.startswith("sha256$"):
            try:
                _algo, salt, hexdigest = stored_hash.split("$", 2)
                calc = hashlib.sha256((salt + plain).encode("utf-8")).hexdigest()
                return _constant_time_eq(calc, hexdigest)
            except Exception:
                return False

        # Plain compare fallback (not recommended in prod)
        return _constant_time_eq(plain, stored_hash)
    except Exception as e:
        logger.error("Password verify error: %s", e)
        return False


def _is_safe_next(next_url: Optional[str]) -> bool:
    if not next_url:
        return False
    if next_url.startswith("//") or "://" in next_url:
        return False
    return next_url.startswith("/")


async def _get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Return a minimal safe user dict or None.
    Tries DB if User exists; otherwise returns a dummy from session/email.
    """
    uid = request.session.get("user_id")
    if not uid:
        return None
    # If you have a User model, attempt to load it.
    if User:
        try:
            async with get_session() as session:
                row = await session.execute(select(User).where(getattr(User, "id") == uid))
                u = row.scalars().first()
                if u is not None:
                    # build a small safe dict (avoid template touching missing attrs)
                    return {
                        "id": getattr(u, "id", uid),
                        "email": getattr(u, "email", request.session.get("user_email", "")),
                        "name": getattr(u, "name", getattr(u, "full_name", "")) or "",
                    }
        except Exception as e:
            logger.warning("User lookup failed; continuing with session user. %s", e)
    # Fallback from session only
    return {
        "id": int(uid),
        "email": request.session.get("user_email", ""),
        "name": "",
    }

# ──────────────────────────────────────────────────────────────────────────────
# Dates & analytics helpers (unchanged)
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_DAYS = 30
NEW_REVIEW_DAYS = 7
_RATING_PROXY = {5: 0.8, 4: 0.4, 3: 0.0, 2: -0.4, 1: -0.8}
_STOPWORDS = {
    "the","and","to","a","an","in","is","it","of","for","on","was","with","at",
    "this","that","by","be","from","as","are","were","or","we","you","they","our",
    "your","their","but","so","if","too","very","can","could","would","will",
    "has","have","had","do","did","does","just","also","than","then","there","here",
    "about","into","out","over","under","between","after","before","during","more","most",
    "less","least","again","ever","never","always","some","any","much","many","few","lot","lots"
}
_NEGATORS = {"not","never","no","hardly","barely","scarcely","without","lack","lacking"}
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

_ASPECT_LEX = {
    "Service": {"service","staff","waiter","host","attendant","attentive","rude","polite","friendly","unprofessional","helpful"},
    "Product Quality": {"quality","taste","fresh","stale","clean","hygiene","delicious","burnt","undercooked","spoiled"},
    "Pricing": {"price","pricing","expensive","cheap","affordable","overpriced","value","cost"},
    "Delivery": {"delivery","deliver","delivered","takeaway","pickup","late","delay","on time","fast","quick"},
}
_URGENT_TERMS = {
    "refund","fraud","scam","unsafe","health","hygiene","lawsuit","legal","threat",
    "hazard","poison","sick","food poisoning","expired","broken glass","fire","electrical"
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
    return _range_or_default(start, end, DEFAULT_DAYS)

def _date_col() -> Any:
    base = getattr(Review, "google_review_time", None)
    created = getattr(Review, "created_at", None)
    if base is not None and created is not None:
        return cast(func.coalesce(Review.google_review_time, Review.created_at), Date)
    return cast(Review.google_review_time, Date)

def _ts_col() -> Any:
    base = getattr(Review, "google_review_time", None)
    created = getattr(Review, "created_at", None)
    if base is not None and created is not None:
        return func.coalesce(Review.google_review_time, Review.created_at)
    return Review.google_review_time

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

def _clamp(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))

def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    toks = [t.lower() for t in _TOKEN_RE.findall(text)]
    out: List[str] = []
    for t in toks:
        if len(t) <= 2:
            continue
        if t in _NEGATORS:
            out.append(t)
            continue
        if t in _STOPWORDS:
            continue
        out.append(t)
    return out

def _bigrams(tokens: List[str]) -> List[str]:
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]

def _lexicon_sentiment_with_negation(tokens: List[str]) -> float:
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
# Login / Logout
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: Optional[str] = None):
    if request.session.get("user_id"):
        dest = next if _is_safe_next(next) else "/dashboard"
        return RedirectResponse(url=dest, status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request, "next": next, "error": None})

@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(None),
):
    email_norm = (email or "").strip().lower()
    pwd = password or ""
    authed_user_id: Optional[int] = None

    # DB user (if User model exists)
    if User:
        try:
            async with get_session() as session:
                row = await session.execute(select(User).where(getattr(User, "email") == email_norm))
                u = row.scalars().first()
                if u is not None:
                    stored_hash = None
                    for field in ("password_hash", "hashed_password", "password"):
                        if hasattr(u, field):
                            stored_hash = getattr(u, field); break
                    if stored_hash and _verify_password(pwd, str(stored_hash)):
                        for field in ("id", "user_id", "pk"):
                            if hasattr(u, field):
                                authed_user_id = int(getattr(u, field)); break
                        if authed_user_id is None:
                            authed_user_id = 1
        except Exception as e:
            logger.warning("User lookup failed during login: %s", e)

    # ENV fallback (bootstrap)
    if authed_user_id is None:
        env_email = os.getenv("ADMIN_EMAIL") or ""
        env_password = os.getenv("ADMIN_PASSWORD") or ""
        if env_email and env_password and _constant_time_eq(email_norm, env_email.lower()) and _constant_time_eq(pwd, env_password):
            authed_user_id = 1

    if authed_user_id is None:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "next": next, "error": "Invalid email or password."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    request.session["user_id"] = authed_user_id
    request.session["user_email"] = email_norm
    dest = next if _is_safe_next(next) else "/dashboard"
    return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)

@router.post("/logout")
async def logout(request: Request, next: Optional[str] = None):
    request.session.clear()
    dest = next if _is_safe_next(next) else "/login"
    return RedirectResponse(url=dest, status_code=status.HTTP_302_FOUND)

# ──────────────────────────────────────────────────────────────────────────────
# Robust /dashboard route (defensive, template-safe)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, company_id: Optional[int] = Query(None)):
    # Auth gate: redirect if not logged in
    if not request.session.get("user_id"):
        target = f"/dashboard{f'?company_id={company_id}' if company_id else ''}"
        return RedirectResponse(url=f"/login?next={target}", status_code=status.HTTP_302_FOUND)

    # Build safe context with defaults
    current_user = None
    companies: List[Company] = []
    active_company_id: Optional[int] = None

    try:
        current_user = await _get_current_user(request)
        async with get_session() as session:
            res = await session.execute(select(Company).order_by(Company.name))
            companies = res.scalars().all() or []

        # Active company
        if company_id is not None:
            active_company_id = int(company_id)
        elif companies:
            active_company_id = int(companies[0].id)
        else:
            active_company_id = None

        ctx = {
            "request": request,
            "user": current_user,              # safe: may be None; template should not assume fields
            "companies": companies or [],      # safe default list
            "active_company_id": active_company_id,
        }
        try:
            return templates.TemplateResponse("dashboard.html", ctx)
        except Exception as te:
            logger.exception("Template rendering error on /dashboard")
            # Fallback diagnostic page (prevents bare 500)
            html = f"<h2>Dashboard</h2><p>Template error: {str(te)}</p>"
            return HTMLResponse(html, status_code=500)

    except Exception as e:
        logger.exception("Dashboard route error")
        return HTMLResponse(f"Error loading dashboard: {str(e)}", status_code=500)

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
    return {"volume": vol["series"], "rating": rat["series"], "sentiment": sen["series"], "window": vol["window"]}

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
# v2: compact summary + keywords (Executive Summary & Keywords cards)
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

# ──────────────────────────────────────────────────────────────────────────────
# Helpers for dashboard aggregation
# ──────────────────────────────────────────────────────────────────────────────
def _group_series(series: List[Dict[str, Any]], group_by: str) -> List[Dict[str, Any]]:
    """Group a daily series by day/week/month. For week we use ISO week; for month we use YYYY-MM.
    For counts we sum; for averages the caller should pass appropriate reducer.
    """
    if group_by == "day":
        return series

    buckets: Dict[str, List[float]] = defaultdict(list)
    # we preserve order by sorting dates
    for item in sorted(series, key=lambda x: x["date"]):
        dt = datetime.strptime(item["date"], "%Y-%m-%d").date()
        key = None
        if group_by == "week":
            iso_year, iso_week, _ = dt.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
        elif group_by == "month":
            key = f"{dt.year}-{dt.month:02d}"
        else:
            key = item["date"]
        buckets[key].append(float(item["value"]))

    # For counts, caller will sum; for averages, caller will average.
    # Here we store sum in 'value' and retain 'n' for optional averaging outside
    grouped = []
    for k in buckets.keys():
        grouped.append({"label": k, "value_sum": float(sum(buckets[k])), "value_avg": float(sum(buckets[k]) / max(len(buckets[k]), 1)), "n": len(buckets[k])})
    # preserve chronological order using label sort heuristic
    def _key_order(lbl: str) -> Tuple[int, int]:
        if group_by == "week":
            y, w = lbl.split("-W")
            return (int(y), int(w))
        if group_by == "month":
            y, m = lbl.split("-")
            return (int(y), int(m))
        # day
        d = datetime.strptime(lbl, "%Y-%m-%d").date()
        return (d.year, d.timetuple().tm_yday)

    grouped.sort(key=lambda x: _key_order(x["label"]))
    return grouped


def _to_line_series_from_grouped(grouped: List[Dict[str, Any]], kind: str = "count") -> List[Dict[str, Any]]:
    out = []
    for g in grouped:
        if kind == "avg":
            out.append({"label": g["label"], "value": round(float(g["value_avg"]), 3)})
        else:
            out.append({"label": g["label"], "value": int(round(float(g["value_sum"])) )})
    return out


def _rolling_average(series: List[Dict[str, Any]], window: int) -> List[Dict[str, Any]]:
    """Compute rolling average on an ordered daily series; if labels not dates, we just slide over order."""
    if window <= 1:
        return [{"date": s.get("date") or s.get("label"), "value": float(s["value"]) } for s in series]
    vals = [float(s["value"]) for s in series]
    out: List[Dict[str, Any]] = []
    for i in range(len(vals)):
        start = max(0, i - window + 1)
        chunk = vals[start:i+1]
        avg = sum(chunk) / len(chunk)
        out.append({"date": series[i].get("date") or series[i].get("label"), "value": round(float(avg), 3)})
    return out


async def _recent_reviews(company_id: int, start: date, end: date, limit: int = 50) -> List[Dict[str, Any]]:
    async with get_session() as session:
        dc = _date_col()
        rows = (await session.execute(
            select(
                Review.id,
                Review.author_name,
                Review.rating,
                Review.text,
                Review.sentiment_score,
                Review.google_review_time,
                Review.profile_photo_url,
            )
            .where(and_(Review.company_id == company_id, dc >= start, dc <= end))
            .order_by(desc(_ts_col()))
            .limit(limit)
        )).all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        text = r.text or ""
        s_val = float(r.sentiment_score) if (r.sentiment_score is not None and abs(float(r.sentiment_score)) >= 1e-9) else _safe_sentiment(text, r.rating)
        out.append({
            "id": r.id,
            "author": r.author_name or "Anonymous",
            "rating": int(r.rating or 0),
            "sentiment": round(float(s_val), 3),
            "label": _label_from_score(s_val),
            "time": r.google_review_time.strftime("%Y-%m-%d") if isinstance(r.google_review_time, datetime) else (str(r.google_review_time) if r.google_review_time else ""),
            "text": (text[:500] + ("…" if len(text) > 500 else "")),
            "avatar": r.profile_photo_url or "",
        })
    return out


async def _company_kpis_block(request: Request, company_id: int, start: Optional[str], end: Optional[str]) -> Dict[str, Any]:
    k = await api_kpis(request, company_id, start, end)
    dist = await api_ratings_distribution(request, company_id, start, end)
    share = await api_sentiment_share(request, company_id, start, end)
    return {
        "kpis": k,
        "ratings_distribution": dist["distribution"],
        "sentiment_share": share["counts"],
    }

# ──────────────────────────────────────────────────────────────────────────────
# New consolidated /api/dashboard endpoint
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard")
async def api_dashboard(
    request: Request,
    company_id: int = Query(..., description="Primary company id"),
    start: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    group_by: str = Query("day", regex="^(day|week|month)$", description="Grouping for trends"),
    limit_reviews: int = Query(20, ge=1, le=200, description="Limit recent reviews returned"),
    competitor_names: Optional[str] = Query(None, description="Comma-separated competitor name filters (ILIKE)"),
    company_ids: Optional[str] = Query(None, description="Optional comma-separated extra company IDs for multi-company view"),
    rolling_window: Optional[int] = Query(None, description="Override rolling window size (default: 7 for day, 3 otherwise)"),
    ai: bool = Query(False, description="Enable AI-generated summary when available"),
):
    """All-in-one dashboard API (async), designed for frontend charts.

    Satisfies requirements: KPIs, series, distributions, sentiment, rolling averages,
    competitor comparisons, multi-company, export-ready blocks, and robust defaults.
    """
    _require_user(request)

    async with get_session() as session:
        base_company = await session.get(Company, company_id)
        if not base_company:
            raise HTTPException(status_code=404, detail="Company not found")

    s, e = await _auto_range_last30(company_id, start, end)

    # Base company core series
    vol = await api_series_reviews(request, company_id, start, end)
    rat = await api_series_ratings(request, company_id, start, end)
    sen = await api_sentiment_series(request, company_id, start, end)

    # Grouping
    g_reviews = _group_series(vol["series"], group_by)
    g_rating = _group_series(rat["series"], group_by)
    g_sent = _group_series(sen["series"], group_by)

    grouped_volume = _to_line_series_from_grouped(g_reviews, kind="count")
    grouped_rating = _to_line_series_from_grouped(g_rating, kind="avg")
    grouped_sentiment = _to_line_series_from_grouped(g_sent, kind="avg")

    # Rolling average (daily -> 7, else -> 3 by default)
    default_window = 7 if group_by == "day" else 3
    rwin = int(rolling_window or default_window)
    rolling_rating = _rolling_average(
        [{"label": x.get("label", x.get("date")), "value": x["value"], "date": x.get("date", x.get("label"))} for x in grouped_rating],
        window=rwin,
    )

    # KPIs, dist, share
    kpis_block = await _company_kpis_block(request, company_id, start, end)

    # Recent reviews sample
    recent = await _recent_reviews(company_id, s, e, limit=limit_reviews)

    # Competitors by names (ILIKE any), optional
    competitors: List[Dict[str, Any]] = []
    names = []
    if competitor_names:
        names = [n.strip() for n in competitor_names.split(',') if n.strip()]
    extra_ids: List[int] = []
    if company_ids:
        try:
            extra_ids = [int(x.strip()) for x in company_ids.split(',') if x.strip()]
        except Exception:
            logger.warning("Invalid company_ids query param; expected comma-separated ints.")
            extra_ids = []

    # Fetch competitor companies by name filter or explicit IDs
    comp_candidates: List[Company] = []
    async with get_session() as session:
        q = select(Company).where(Company.id != company_id)
        if names:
            # Build ILIKE OR conditions
            ors = []
            for n in names:
                try:
                    ors.append(Company.name.ilike(f"%{n}%"))
                except Exception:
                    pass
            if ors:
                q = q.where(or_(*ors))  # type: ignore
        if extra_ids:
            q = q.where(Company.id.in_(extra_ids))
        q = q.order_by(Company.name).limit(10)
        try:
            comp_candidates = (await session.execute(q)).scalars().all() or []
        except Exception as ex:
            # Some DBs might not support ILIKE; fallback to LIKE
            logger.info("ILIKE not supported; falling back to LIKE for competitor search. %s", ex)
            if names:
                q2 = select(Company).where(Company.id != company_id)
                ors2 = []
                for n in names:
                    ors2.append(Company.name.like(f"%{n}%"))
                q2 = q2.where(or_(*ors2)).order_by(Company.name).limit(10)  # type: ignore
                comp_candidates = (await session.execute(q2)).scalars().all() or []
            else:
                comp_candidates = []

    # Compose competitor metrics (lightweight to keep perf)
    for comp in comp_candidates:
        try:
            c_kpis = await _company_kpis_block(request, int(comp.id), start, end)
            c_vol = await api_series_reviews(request, int(comp.id), start, end)
            g_c_rev = _group_series(c_vol["series"], group_by)
            competitors.append({
                "company": {"id": int(comp.id), "name": comp.name},
                "kpis": c_kpis["kpis"],
                "ratings_distribution": c_kpis["ratings_distribution"],
                "sentiment_share": c_kpis["sentiment_share"],
                "trends": {
                    "volume": _to_line_series_from_grouped(g_c_rev, kind="count"),
                },
            })
        except Exception as ex:
            logger.warning("Competitor metric build failed for %s: %s", getattr(comp, 'name', comp), ex)

    # Multi-company view (explicit list)
    multi_companies: List[Dict[str, Any]] = []
    if extra_ids:
        ids = [cid for cid in extra_ids if cid != company_id and cid not in [int(c.get("company", {}).get("id", -1)) for c in competitors]]
        for cid in ids[:10]:
            try:
                c_kpis = await _company_kpis_block(request, cid, start, end)
                multi_companies.append({"company_id": cid, **c_kpis})
            except Exception as ex:
                logger.info("Skipping multi-company id %s: %s", cid, ex)

    # Optional AI summary
    ai_summary: Optional[Dict[str, Any]] = None
    if ai and _ai_summarize_dashboard:
        try:
            ai_summary = await _ai_summarize_dashboard({
                "company_id": company_id,
                "window": {"start": str(s), "end": str(e)},
                "kpis": kpis_block["kpis"],
                "trends": {
                    "volume": grouped_volume,
                    "rating": grouped_rating,
                    "sentiment": grouped_sentiment,
                    "rolling_rating": rolling_rating,
                },
                "distribution": kpis_block["ratings_distribution"],
                "sentiment_share": kpis_block["sentiment_share"],
                "recent_reviews": recent,
                "competitors": competitors,
            })
        except Exception as ex:
            logger.info("AI summary disabled due to error: %s", ex)
            ai_summary = None

    response: Dict[str, Any] = {
        "window": {"start": str(s), "end": str(e)},
        "company": {"id": int(company_id), "name": getattr(base_company, "name", "")},
        "group_by": group_by,
        "kpis": kpis_block["kpis"],
        "charts": {
            "line": {
                "volume": grouped_volume,
                "rating": grouped_rating,
                "sentiment": grouped_sentiment,
                "rolling_rating": rolling_rating,
            },
            "bar": {
                "ratings_distribution": kpis_block["ratings_distribution"],
            },
            "pie": {
                "sentiment_share": kpis_block["sentiment_share"],
            },
        },
        "trends": {
            "daily": (await api_series_overview(request, company_id, start, end)) if group_by == "day" else None,
        },
        "recent_reviews": recent,
        "competitors": competitors,
        "multi_companies": multi_companies,
        "ai_summary": ai_summary,
        "export_summary": {
            "company_id": int(company_id),
            "company_name": getattr(base_company, "name", ""),
            "start": str(s),
            "end": str(e),
            "total_reviews": kpis_block["kpis"]["total_reviews"],
            "avg_rating": kpis_block["kpis"]["avg_rating"],
            "avg_sentiment": kpis_block["kpis"]["avg_sentiment"],
            "new_reviews": kpis_block["kpis"]["new_reviews"],
            "positive": kpis_block["sentiment_share"].get("positive", 0),
            "neutral": kpis_block["sentiment_share"].get("neutral", 0),
            "negative": kpis_block["sentiment_share"].get("negative", 0),
        },
    }

    return JSONResponse(response)
