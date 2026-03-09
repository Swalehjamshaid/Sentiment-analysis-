# filename: app/routes/reviews.py
from __future__ import annotations

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta, date, time
from collections import Counter

from fastapi import APIRouter, Query, Depends, HTTPException, Request
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import OutscraperReviewsService, ReviewData

DEFAULT_DAYS = 30

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _normalize_window(start: Optional[str], end: Optional[str]) -> Tuple[datetime, datetime]:
    """
    Handles dashboard date filters.
    - If empty → last 30 days
    - Accepts YYYY-MM-DD or ISO strings
    """
    def _parse(val: Optional[str]):
        if not val:
            return None
        try:
            if len(val) == 10:
                return datetime.strptime(val, "%Y-%m-%d")
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return None

    s = _parse(start)
    e = _parse(end)

    if not s and not e:
        e = datetime.combine(date.today(), datetime.max.time())
        s = e - timedelta(days=DEFAULT_DAYS - 1)

    if s and not e:
        e = datetime.combine(date.today(), datetime.max.time())
    if e and not s:
        s = e - timedelta(days=DEFAULT_DAYS - 1)

    # Normalize to day bounds (inclusive)
    s = datetime.combine(s.date(), time.min)
    e = datetime.combine(e.date(), time.max)

    if s > e:
        s, e = e, s

    return s, e


def _resolve_dt_col():
    """Pick correct datetime column depending on DB schema."""
    if hasattr(Review, "google_review_time"):
        return Review.google_review_time
    if hasattr(Review, "review_date"):
        return Review.review_date
    if hasattr(Review, "created_at"):
        return Review.created_at
    return Review.id


# -------------------------------------------------------------------
# NEW — REQUIRED BY FRONT-END
# /api/reviews/list
# -------------------------------------------------------------------

@router.get("/list")
async def reviews_list(
    company_id: int = Query(...),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    sort: str = Query("newest", regex="^(newest|oldest|highest|lowest)$"),
    limit: int = Query(200, ge=20, le=2000),
    db: AsyncSession = Depends(get_session),
):
    """
    EXACT response expected by Dashboard front-end.
    """
    s, e = _normalize_window(start, end)
    dtcol = _resolve_dt_col()

    # Sorting
    if sort == "oldest":
        order = [dtcol.asc()]
    elif sort == "highest":
        order = [Review.rating.desc(), dtcol.desc()] if hasattr(Review, "rating") else [dtcol.desc()]
    elif sort == "lowest":
        order = [Review.rating.asc(), dtcol.desc()] if hasattr(Review, "rating") else [dtcol.desc()]
    else:
        order = [dtcol.desc()]

    stmt = (
        select(Review)
        .where(
            Review.company_id == company_id,
            dtcol >= s,
            dtcol <= e,
        )
        .order_by(*order)
        .limit(limit)
    )

    rows = (await db.execute(stmt)).scalars().all()

    def _fmt_dt(v):
        if not v:
            return ""
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d")
        try:
            return str(v)[:10]
        except Exception:
            return str(v)

    items = []
    for r in rows:
        items.append({
            "author_name": (getattr(r, "author_name", None) or getattr(r, "author", None) or "Anonymous"),
            "rating": int(getattr(r, "rating", 0) or 0),
            "text": getattr(r, "text", None) or getattr(r, "review_text", None) or "",
            "review_time": _fmt_dt(
                getattr(r, "google_review_time", None)
                or getattr(r, "review_date", None)
                or getattr(r, "created_at", None)
            ),
            "profile_photo_url": getattr(r, "profile_photo_url", "") or "",
        })

    return {"items": items}


# -------------------------------------------------------------------
# (KEPT) /api/reviews/ingest — used by Admin/Batch Sync
# -------------------------------------------------------------------

@router.post("/ingest")
async def ingest_reviews(
    request: Request,
    place_id: str,
    company_id: int,
    competitor_place_ids: Optional[List[str]] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(500, ge=50, le=5000),
    db: AsyncSession = Depends(get_session),
):
    """
    Ingest external reviews into database.
    """
    result = await db.execute(select(Company).filter(Company.id == company_id))
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    s, e = _normalize_window(start_date, end_date)

    entities = [place_id] + (competitor_place_ids or [])

    client = getattr(request.app.state, "google_reviews_client", None)
    if client is None:
        raise HTTPException(status_code=501, detail="google_reviews_client missing")

    service = OutscraperReviewsService(client)

    total_saved = 0
    total_fetched = 0

    for pid in entities:
        data: List[ReviewData] = service.fetch_reviews(
            place_id=pid,
            start_date=s,
            end_date=e,
            max_reviews=limit
        )

        total_fetched += len(data)

        for r in data:
            dt_val = r.time_created

            # Duplicate detection:
            # Prefer an external_review_id/google_review_id if your model has it,
            # otherwise fallback to (company_id, author_name, time)
            dedup_done = False
            for id_field in ("external_review_id", "google_review_id"):
                if hasattr(Review, id_field) and r.review_id:
                    existing = await db.execute(
                        select(Review).where(getattr(Review, id_field) == r.review_id)
                    )
                    if existing.scalars().first():
                        dedup_done = True
                        break
            if dedup_done:
                continue

            if not dedup_done:
                existing = await db.execute(
                    select(Review).where(
                        and_(
                            Review.company_id == company_id,
                            Review.author_name == (r.author_name or "Anonymous"),
                            _resolve_dt_col() == dt_val,
                        )
                    )
                )
                if existing.scalars().first():
                    continue

            row = Review()
            # Mandatory
            row.company_id = company_id
            row.author_name = r.author_name or "Anonymous"
            row.rating = r.rating
            row.text = r.text

            # Datetime (set both if your model has both)
            if hasattr(Review, "google_review_time"):
                row.google_review_time = dt_val
            if hasattr(Review, "review_date"):
                row.review_date = dt_val

            # IDs if available
            if hasattr(Review, "external_review_id"):
                row.external_review_id = r.review_id
            if hasattr(Review, "google_review_id"):
                row.google_review_id = r.review_id

            # Optional fields
            if hasattr(Review, "profile_photo_url"):
                row.profile_photo_url = (r.additional_fields or {}).get("profile_photo_url")
            if hasattr(Review, "competitor_name"):
                row.competitor_name = r.competitor_name
            if hasattr(Review, "source_platform"):
                row.source_platform = r.source_platform or "Google"
            elif hasattr(Review, "platform"):
                row.platform = r.source_platform or "Google"

            db.add(row)
            total_saved += 1

    await db.commit()

    return {
        "status": "success",
        "reviews_fetched": total_fetched,
        "reviews_saved": total_saved,
    }


# -------------------------------------------------------------------
# (LEGACY) /api/reviews/feed/{company_id}
# -------------------------------------------------------------------

@router.get("/feed/{company_id}")
async def reviews_feed_legacy(
    company_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_session),
):
    """
    Older pages still use this.
    """
    s, e = _normalize_window(start_date, end_date)
    dtcol = _resolve_dt_col()

    stmt = (
        select(Review)
        .where(
            Review.company_id == company_id,
            dtcol >= s,
            dtcol <= e,
        )
        .order_by(dtcol.desc())
        .limit(limit)
    )

    rows = (await db.execute(stmt)).scalars().all()

    def _fmt(v):
        try:
            return v.isoformat()
        except Exception:
            return str(v)

    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "author_name": r.author_name,
            "rating": r.rating,
            "text": r.text,
            "review_time": _fmt(getattr(r, "google_review_time", None) or getattr(r, "review_date", None)),
            "profile_photo_url": getattr(r, "profile_photo_url", None),
        })

    return {"reviews": out}


# -------------------------------------------------------------------
# (OPTIONAL) Competitor analytics
# -------------------------------------------------------------------

@router.get("/competitors/{company_id}")
async def competitor_stats(
    company_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    """
    Used in future competitor analysis pages.
    """
    s, e = _normalize_window(start_date, end_date)
    dtcol = _resolve_dt_col()

    stmt = (
        select(Review)
        .where(
            Review.company_id == company_id,
            Review.competitor_name != None,  # noqa: E711
            dtcol >= s,
            dtcol <= e,
        )
    )

    rows = (await db.execute(stmt)).scalars().all()

    counts = Counter(r.competitor_name for r in rows if r.competitor_name)
    ratings: Dict[str, List[float]] = {}

    for r in rows:
        if r.competitor_name and r.rating is not None:
            ratings.setdefault(r.competitor_name, []).append(float(r.rating))

    rating_avg = {
        k: round(sum(v) / len(v), 2)
        for k, v in ratings.items()
    }

    return {
        "competitor_review_count": dict(counts),
        "competitor_avg_rating": rating_avg
    }
