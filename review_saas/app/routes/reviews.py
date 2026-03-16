# filename: app/routes/reviews.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Request, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, desc

from app.core.db import get_session
from app.core.models import Review, Company
from app.services.review import ingest_outscraper_reviews  # Make sure this exists

logger = logging.getLogger("app.reviews")

router = APIRouter(prefix="/api", tags=["reviews"])


# ─────────────────────────────────────────
# Auth helper
# ─────────────────────────────────────────
def _require_user(request: Request) -> None:
    if not request.session.get("user"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized"
        )


# ─────────────────────────────────────────
# Fetch reviews for a company
# ─────────────────────────────────────────
@router.get("/reviews")
async def get_reviews(
    request: Request,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50
):
    _require_user(request)

    async with get_session() as session:
        stmt = select(Review).where(Review.company_id == company_id)

        if start:
            stmt = stmt.where(Review.created_at >= datetime.fromisoformat(start))
        if end:
            stmt = stmt.where(Review.created_at <= datetime.fromisoformat(end))

        stmt = stmt.order_by(desc(Review.created_at)).limit(limit)

        result = await session.execute(stmt)
        reviews = result.scalars().all()

        return [
            {
                "id": r.id,
                "company_id": r.company_id,
                "rating": r.rating,
                "text": r.text,
                "author": r.author,
                "created_at": r.created_at.isoformat()
            }
            for r in reviews
        ]


# ─────────────────────────────────────────
# Add a new review (manual POST)
# ─────────────────────────────────────────
@router.post("/reviews")
async def add_review(
    request: Request,
    company_id: int,
    rating: float,
    text: str,
    author: Optional[str] = "Anonymous"
):
    _require_user(request)

    async with get_session() as session:
        company = await session.get(Company, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        new_review = Review(
            company_id=company_id,
            rating=rating,
            text=text,
            author=author,
            created_at=datetime.utcnow()
        )
        session.add(new_review)
        await session.commit()
        await session.refresh(new_review)

        return {
            "status": "ok",
            "review": {
                "id": new_review.id,
                "company_id": new_review.company_id,
                "rating": new_review.rating,
                "text": new_review.text,
                "author": new_review.author,
                "created_at": new_review.created_at.isoformat()
            }
        }


# ─────────────────────────────────────────
# Trigger Outscraper review ingestion
# ─────────────────────────────────────────
@router.post("/reviews/sync")
async def sync_reviews(
    request: Request,
    background: BackgroundTasks,
    company_id: int
):
    _require_user(request)

    async with get_session() as session:
        company = await session.get(Company, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        if not ingest_outscraper_reviews:
            raise HTTPException(status_code=503, detail="Outscraper service not available")

        # Run in background to fetch reviews
        background.add_task(ingest_outscraper_reviews, company, session)

        return {"status": "sync_started", "company_id": company_id}
