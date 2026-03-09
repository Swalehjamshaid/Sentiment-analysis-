# filename: app/routes/reviews.py
from __future__ import annotations

from typing import List, Optional, Dict, Any, Tuple
from collections import Counter
from datetime import datetime, timedelta, date, time

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import OutscraperReviewsService, ReviewData

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
DEFAULT_DAYS = 30

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def _normalize_window(start_date: Optional[str], end_date: Optional[str]) -> Tuple[datetime, datetime]:
    """
    Converts start/end into datetime objects.
    If both missing → default last 30 days.
    Handles YYYY-MM-DD or ISO strings.
    """
    def _parse(s: Optional[str]):
        if not s:
            return None
        try:
            if len(s) == 10:
                return datetime.strptime(s, "%Y-%m-%d")
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except:
            return None

    s = _parse(start_date)
    e = _parse(end_date)

    # Default last 30 days
    if not s and not e:
        e = datetime.combine(date.today(), datetime.max.time())
        s = e - timedelta(days=DEFAULT_DAYS - 1)

    if s and not e:
        e = datetime.combine(date.today(), datetime.max.time())
    if e and not s:
        s = e - timedelta(days=DEFAULT_DAYS - 1)

    # Normalize
    if s.tzinfo:
        s = s.replace(tzinfo=None)
    if e.tzinfo:
        e = e.replace(tzinfo=None)

    s = datetime.combine(s.date(), time.min)
    e = datetime.combine(e.date(), time.max)

    if s > e:
        s, e = e, s

    return s, e


def _resolve_date_col():
    """
    Consistent backend → front-end mapping for review time.
    Order of preference:
        google_review_time
        review_date
        created_at
        id (fallback)
    """
    if hasattr(Review, "google_review_time"):
        return Review.google_review_time
    if hasattr(Review, "review_date"):
        return Review.review_date
    if hasattr(Review, "created_at"):
        return Review.created_at
    return Review.id


# ---------------------------------------------------------
# NEW — Matches your front-end:  GET /api/reviews/list
# ---------------------------------------------------------
@router.get("/list")
async def list_reviews(
    company_id: int = Query(...),
    start: Optional[str] = "",
    end: Optional[str] = "",
    sort: str = Query("newest", regex="^(newest|oldest|highest|lowest)$"),
    limit: int = Query(200, ge=10, le=5000),
    db: AsyncSession = Depends(get_session),
):
    """
    EXACT endpoint expected by your dashboard front-end:
        fetch(`/api/reviews/list?...`)
    """

    s, e = _normalize_window(start, end)
    date_col = _resolve_date_col()

    # Sorting rules to match JS
    if sort == "oldest":
        order = [date_col.asc()]
    elif sort == "highest":
        order = [Review.rating.desc().nullslast(), date_col.desc()] if hasattr(Review, "rating") else [date_col.desc()]
    elif sort == "lowest":
        order = [Review.rating.asc().nullslast(), date_col.desc()] if hasattr(Review, "rating") else [date_col.desc()]
    else:
        order = [date_col.desc()]

    q = (
        select(Review)
        .where(
            and_(
                Review.company_id == company_id,
                date_col >= s,
                date_col <= e,
            )
        )
        .order_by(*order)
        .limit(limit)
    )

    result = await db.execute(q)
    rows = result.scalars().all()

    def _fmt(dt):
        if not dt:
            return ""
        try:
            if isinstance(dt, datetime):
                return dt.strftime("%Y-%m-%d")
            return str(dt)[:10]
        except:
            return str(dt)

    items = []
    for r in rows:
        author = getattr(r, "author_name", None) or getattr(r, "author", None) or "Anonymous"
        text = getattr(r, "text", "") or getattr(r, "review_text", "")
        dt = getattr(r, "google_review_time", None) or getattr(r, "review_date", None) or getattr(r, "created_at", None)
        rating = getattr(r, "rating", None)
        photo = getattr(r, "profile_photo_url", "") or ""

        items.append({
            "author_name": author,
            "rating": rating,
            "text": text,
            "review_time": _fmt(dt),
            "profile_photo_url": photo,
        })

    return {"items": items}


# ---------------------------------------------------------
# REVIEW INGEST (kept unchanged)
# ---------------------------------------------------------
@router.post("/ingest")
async def ingest_reviews(
    request: Request,
    place_id: str,
    company_id: int,
    competitor_place_ids: Optional[List[str]] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=50000),
    db: AsyncSession = Depends(get_session),
):
    """
    Fetch reviews via Outscraper/Google and store them.
    """
    try:
        company = (await db.execute(select(Company).where(Company.id == company_id))).scalars().first()
        if not company:
            raise HTTPException(404, "Company not found")

        s, e = _normalize_window(start_date, end_date)

        client = request.app.state.google_reviews_client
        if client is None:
            raise HTTPException(501, "google_reviews_client not configured")

        service = OutscraperReviewsService(client)

        total_saved = 0
        total_fetched = 0

        entities = [place_id] + (competitor_place_ids or [])

        for pid in entities:
            reviews: List[ReviewData] = service.fetch_reviews(
                place_id=pid,
                start_date=s,
                end_date=e,
                max_reviews=limit,
            )
            total_fetched += len(reviews)

            for r in reviews:
                exists = await db.execute(
                    select(Review).where(
                        and_(
                            Review.company_id == company_id,
                            Review.author_name == r.author_name,
                            Review.google_review_time == r.time_created,
                        )
                    )
                )
                if exists.scalars().first():
                    continue

                m = Review()
                m.company_id = company_id
                m.author_name = r.author_name
                m.rating = r.rating
                m.text = r.text
                m.google_review_time = r.time_created
                m.profile_photo_url = r.additional_fields.get("profile_photo_url") if r.additional_fields else None

                db.add(m)
                total_saved += 1

        await db.commit()

        return {
            "status": "success",
            "fetched": total_fetched,
            "saved": total_saved,
            "window": {"start": str(s), "end": str(e)},
        }

    except Exception as e:
        await db.rollback()
        raise HTTPException(500, str(e))


# ---------------------------------------------------------
# FEED (legacy)
# ---------------------------------------------------------
@router.get("/feed/{company_id}")
async def get_reviews_feed(company_id: int, start_date: Optional[str] = None, end_date: Optional[str] = None,
                           limit: int = 50, db: AsyncSession = Depends(get_session)):
    s, e = _normalize_window(start_date, end_date)
    date_col = _resolve_date_col()

    q = (
        select(Review)
        .where(
            and_(
                Review.company_id == company_id,
                date_col >= s,
                date_col <= e,
            )
        )
        .order_by(date_col.desc())
        .limit(limit)
    )

    result = await db.execute(q)
    rows = result.scalars().all()

    out = []
    for r in rows:
        dt = getattr(r, "google_review_time", None)
        author = getattr(r, "author_name", None)
        out.append({
            "author_name": author,
            "rating": r.rating,
            "text": r.text,
            "review_time": str(dt) if dt else "",
        })

    return {"reviews": out}


# ---------------------------------------------------------
# COMPETITOR STATS (legacy)
# ---------------------------------------------------------
@router.get("/competitors/{company_id}")
async def competitor_stats(company_id: int,
                           start_date: Optional[str] = None,
                           end_date: Optional[str] = None,
                           db: AsyncSession = Depends(get_session)):
    s, e = _normalize_window(start_date, end_date)

    q = select(Review).where(
        and_(
            Review.company_id == company_id,
            Review.competitor_name != None,
        )
    )

    result = await db.execute(q)
    rows = result.scalars().all()

    counts = Counter(r.competitor_name for r in rows)
    ratings: Dict[str, List[float]] = {}

    for r in rows:
        if r.competitor_name and r.rating:
            ratings.setdefault(r.competitor_name, []).append(float(r.rating))

    avg_rating = {k: round(sum(v) / len(v), 2) for k, v in ratings.items()}

    return {
        "window": {"start": str(s), "end": str(e)},
        "competitor_review_count": dict(counts),
        "competitor_avg_rating": avg_rating,
    }
