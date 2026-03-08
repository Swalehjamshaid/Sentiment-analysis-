# filename: app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Optional, Dict, Any
from collections import Counter
from datetime import datetime, timedelta, date

from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import OutscraperReviewsService, ReviewData

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
DEFAULT_DAYS = 30

# ---------------------------------------------------------
# Mock API client (Replace with real Outscraper client)
# ---------------------------------------------------------
class MockClient:
    def get_reviews(self, place_id, limit, offset):
        return {
            "reviews": [
                {
                    "review_id": f"rev_{offset+i}",
                    "author_name": f"Author {i}",
                    "rating": 3 + (i % 3),
                    "text": f"Sample review {i}",
                    "time": 1700000000 + (i * 2000),
                    "title": f"Title {i}",
                    "helpful_votes": i % 3,
                    "platform": "Google",
                    "competitor_name": f"Competitor {i%2}" if i % 2 == 0 else None,
                    "profile_photo_url": None,
                } for i in range(limit)
            ]
        }

# ---------------------------------------------------------
# Initialize services
# ---------------------------------------------------------
api_client = MockClient()
outscraper_service = OutscraperReviewsService(api_client)

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def _parse_iso(d: Optional[str]) -> Optional[datetime]:
    if not d:
        return None
    # Accept YYYY-MM-DD or full ISO string
    try:
        if len(d) == 10:
            return datetime.fromisoformat(d)
        return datetime.fromisoformat(d.replace("Z", "+00:00"))
    except Exception:
        return None

def _last30_window() -> (datetime, datetime):
    end_dt = datetime.combine(date.today(), datetime.max.time())
    start_dt = end_dt - timedelta(days=DEFAULT_DAYS - 1)
    return start_dt, end_dt

def _get_window(start_date: Optional[str], end_date: Optional[str]) -> (Optional[datetime], Optional[datetime]):
    s = _parse_iso(start_date)
    e = _parse_iso(end_date)
    if s or e:
        # if only one side provided, fill the other as needed
        if not e:
            e = datetime.combine(date.today(), datetime.max.time())
        if not s:
            s = e - timedelta(days=DEFAULT_DAYS - 1)
        if s > e:
            s, e = e, s
        return s, e
    # default to last 30 days
    return _last30_window()

def _set_if_has(obj: Any, field: str, value: Any):
    if hasattr(obj, field):
        setattr(obj, field, value)

# ---------------------------------------------------------
# Ingest Reviews Based on Date Range (defaults to last 30d)
# ---------------------------------------------------------
@router.post("/ingest")
async def ingest_reviews(
    place_id: str,
    company_id: int,
    competitor_place_ids: Optional[List[str]] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(500),
    db: AsyncSession = Depends(get_session)
):
    """
    Fetch reviews from Outscraper and store them in DB.
    - If start_date/end_date are omitted, defaults to last 30 days.
    - Writes to both field-name variants to remain compatible with existing dashboards.
    """
    try:
        # Validate company
        result = await db.execute(select(Company).filter(Company.id == company_id))
        company = result.scalars().first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        start_dt, end_dt = _get_window(start_date, end_date)

        places = [place_id]
        if competitor_place_ids:
            places.extend(competitor_place_ids)

        total_saved = 0
        total_fetched = 0

        for place in places:
            reviews_data: List[ReviewData] = await outscraper_service.fetch_reviews(place, max_reviews=limit)
            total_fetched += len(reviews_data)

            for r in reviews_data:
                review_date = r.time_created
                if review_date is None and r.time:
                    # If time is UNIX, fallback; else ignore
                    try:
                        review_date = datetime.utcfromtimestamp(int(r.time))
                    except Exception:
                        review_date = None

                # Date filter
                if start_dt and review_date and review_date < start_dt:
                    continue
                if end_dt and review_date and review_date > end_dt:
                    continue

                review_id = r.review_id

                exist = await db.execute(
                    select(Review).filter(
                        getattr(Review, "external_review_id", Review.id) == review_id
                    )
                )
                if exist.scalars().first():
                    continue

                model = Review()
                _set_if_has(model, "company_id", company_id)
                _set_if_has(model, "external_review_id", review_id)
                _set_if_has(model, "author_name", r.author_name)
                _set_if_has(model, "author", r.author_name)
                _set_if_has(model, "rating", r.rating)
                _set_if_has(model, "text", r.text)
                _set_if_has(model, "review_text", r.text)
                _set_if_has(model, "google_review_time", review_date)
                _set_if_has(model, "review_date", review_date)
                _set_if_has(model, "sentiment_score", None)
                _set_if_has(model, "sentiment", None)
                _set_if_has(model, "platform", getattr(r, "platform", "Google"))
                _set_if_has(model, "competitor_name", getattr(r, "competitor_name", None))
                _set_if_has(model, "profile_photo_url", getattr(r, "profile_photo_url", None))

                db.add(model)
                total_saved += 1

        await db.commit()
        return {
            "status": "success",
            "reviews_fetched": total_fetched,
            "reviews_saved": total_saved,
            "date_range": {
                "start_date": start_dt.isoformat() if start_dt else None,
                "end_date": end_dt.isoformat() if end_dt else None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to ingest reviews: {str(e)}")

# ---------------------------------------------------------
# Review Feed for Dashboard (defaults to last 30d)
# ---------------------------------------------------------
@router.get("/feed/{company_id}")
async def get_reviews_feed(
    company_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_session)
):
    """
    Returns filtered reviews for the dashboard.
    - Defaults to last 30 days when dates are not provided.
    - Returns both naming variants to preserve compatibility.
    """
    s, e = _get_window(start_date, end_date)

    query = select(Review).filter(Review.company_id == company_id)
    # Apply date filter on any present datetime column
    # Prefer google_review_time/review_date fields if available
    if hasattr(Review, "google_review_time"):
        if s: query = query.filter(Review.google_review_time >= s)
        if e: query = query.filter(Review.google_review_time <= e)
    elif hasattr(Review, "review_date"):
        if s: query = query.filter(Review.review_date >= s)
        if e: query = query.filter(Review.review_date <= e)

    query = query.order_by(
        (getattr(Review, "google_review_time", getattr(Review, "review_date", Review.id))).desc()
    ).limit(limit)

    result = await db.execute(query)
    reviews = result.scalars().all()

    def _s(dt):
        if not dt: return None
        try:
            return dt.isoformat()
        except Exception:
            return str(dt)

    out = []
    for r in reviews:
        author_name = getattr(r, "author_name", None) or getattr(r, "author", None)
        text = getattr(r, "text", None) or getattr(r, "review_text", None)
        dt = getattr(r, "google_review_time", None) or getattr(r, "review_date", None)
        sentiment = getattr(r, "sentiment_score", None)
        if sentiment is None:
            sentiment = getattr(r, "sentiment", None)
        out.append({
            "id": getattr(r, "id", None),
            "author_name": author_name,
            "author": author_name,                      # duplicate for compatibility
            "rating": getattr(r, "rating", None),
            "text": text,
            "review_text": text,                        # duplicate for compatibility
            "review_time": _s(dt),
            "date": _s(dt),
            "sentiment": sentiment,
            "competitor": getattr(r, "competitor_name", None),
            "competitor_name": getattr(r, "competitor_name", None),
            "platform": getattr(r, "platform", "Google"),
            "profile_photo_url": getattr(r, "profile_photo_url", None)
        })

    return {"status": "success", "reviews": out, "window": {"start": _s(s), "end": _s(e)}}

# ---------------------------------------------------------
# Competitor Analytics API (defaults to last 30d)
# ---------------------------------------------------------
@router.get("/competitors/{company_id}")
async def competitor_stats(
    company_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_session)
):
    """
    Returns competitor review counts and ratings.
    Defaults to last 30 days if not provided.
    """
    s, e = _get_window(start_date, end_date)

    query = select(Review).filter(
        Review.company_id == company_id,
        Review.competitor_name != None  # noqa: E711
    )

    # Date range on known fields
    if hasattr(Review, "google_review_time"):
        if s: query = query.filter(Review.google_review_time >= s)
        if e: query = query.filter(Review.google_review_time <= e)
    elif hasattr(Review, "review_date"):
        if s: query = query.filter(Review.review_date >= s)
        if e: query = query.filter(Review.review_date <= e)

    result = await db.execute(query)
    reviews = result.scalars().all()

    competitor_counts = Counter(
        getattr(r, "competitor_name", None) for r in reviews if getattr(r, "competitor_name", None)
    )

    # Aggregate ratings
    competitor_ratings: Dict[str, List[int]] = {}
    for r in reviews:
        name = getattr(r, "competitor_name", None)
        rating = getattr(r, "rating", None)
        if name and rating is not None:
            competitor_ratings.setdefault(name, []).append(int(rating))

    competitor_avg = {
        name: round(sum(vals) / len(vals), 2) if vals else 0.0
        for name, vals in competitor_ratings.items()
    }

    return {
        "window": {"start": s.isoformat() if s else None, "end": e.isoformat() if e else None},
        "competitor_review_count": dict(competitor_counts),  # convert Counter to dict
        "competitor_avg_rating": competitor_avg
    }
