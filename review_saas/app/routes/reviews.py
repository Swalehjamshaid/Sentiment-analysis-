# filename: app/routes/reviews.py

from __future__ import annotations
from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.outscraper_client import OutscraperReviewsClient
from app.services.google_reviews import ingest_outscraper_reviews

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


# ---- Response shape expected by your UI: { feed: [...] } ----
class ReviewFeedItem(BaseModel):
    author_name: str
    rating: float
    sentiment_score: float
    review_time: str  # YYYY-MM-DD
    text: str


class ReviewFeed(BaseModel):
    feed: List[ReviewFeedItem]


@router.get("", response_model=ReviewFeed)
async def list_reviews(
    company_id: int = Query(..., description="Company ID"),
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    # validate company
    comp = await session.get(Company, company_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Company not found")

    start_d = datetime.fromisoformat(start).date() if start else date.min
    end_d = datetime.fromisoformat(end).date() if end else date.max

    res = await session.execute(
        select(Review)
        .where(
            and_(
                Review.company_id == company_id,
                Review.google_review_time.is_not(None),
                Review.google_review_time >= datetime.combine(start_d, datetime.min.time()),
                Review.google_review_time <= datetime.combine(end_d, datetime.max.time()),
            )
        )
        .order_by(Review.google_review_time.desc())
        .limit(limit)
    )
    rows = res.scalars().all()

    def to_item(r: Review) -> ReviewFeedItem:
        dt = r.google_review_time.date().isoformat() if r.google_review_time else ""
        score = r.sentiment_score if r.sentiment_score is not None else 0.0
        rating = float(r.rating or 0)
        return ReviewFeedItem(
            author_name=r.author_name or "Anonymous",
            rating=rating,
            sentiment_score=float(score),
            review_time=dt,
            text=r.text or "",
        )

    return ReviewFeed(feed=[to_item(r) for r in rows])


# ---- Sync endpoint: fetch from Outscraper, save to DB ----
class ReviewSyncRequest(BaseModel):
    company_id: int = Field(..., ge=1)
    max_reviews: Optional[int] = Field(200, ge=1, le=1000)


@router.post("/sync")
async def sync_reviews(
    payload: ReviewSyncRequest, session: AsyncSession = Depends(get_session)
):
    comp = await session.get(Company, payload.company_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Company not found")

    client = OutscraperReviewsClient()
    raw_payloads = await client.fetch_reviews(comp, max_reviews=payload.max_reviews)

    saved = await ingest_outscraper_reviews(
        session=session,
        company_id=comp.id,
        raw_payloads=raw_payloads if isinstance(raw_payloads, list) else [raw_payloads],
    )

    # Update company's last_synced_at
    comp.last_synced_at = datetime.utcnow()
    await session.commit()

    return {"status": "ok", "company_id": comp.id, "saved": saved}
