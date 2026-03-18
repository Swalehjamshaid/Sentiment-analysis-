# filename: app/routes/reviews.py

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from datetime import datetime
from typing import Optional

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.scraper import fetch_reviews
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

router = APIRouter(prefix="/api/reviews", tags=["reviews"])
logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()

def _safe_parse_iso(dt_str: str) -> datetime:
    """
    Parse ISO 8601 strings robustly, handling 'Z' (UTC) suffix and missing timezone.
    Falls back to naive datetime if necessary.
    """
    if not dt_str:
        return datetime.utcnow()
    try:
        # Handle trailing 'Z'
        if dt_str.endswith("Z"):
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return datetime.fromisoformat(dt_str)
    except Exception:
        # Last resort: strip timezone if present and parse
        try:
            if "+" in dt_str:
                base = dt_str.split("+", 1)[0]
                return datetime.fromisoformat(base)
        except Exception:
            pass
    return datetime.utcnow()

@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    session: AsyncSession = Depends(get_session)
):
    # 1) Validate Company
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    place_id: Optional[str] = company.google_id or company.place_id
    if not place_id:
        raise HTTPException(status_code=400, detail="Missing Google Place ID")

    # 2) Existing count to determine skip window (pagination offset)
    count_stmt = select(func.count(Review.id)).where(Review.company_id == company_id)
    existing_count = (await session.execute(count_stmt)).scalar() or 0
    logger.info(
        f"[reviews.ingest] Company={company.id} {company.name} existing_count={existing_count}"
    )

    # 3) Fetch next batch of 300 using existing_count as 'skip'
    try:
        scraped_data = await fetch_reviews(place_id=place_id, limit=300, skip=existing_count)
    except Exception as e:
        # Maintain endpoint behavior: fail softly and return 0 if scraper hiccups
        logger.error(f"[reviews.ingest] fetch_reviews failed for place_id={place_id}, skip={existing_count}: {e}")
        scraped_data = []

    if not scraped_data:
        return {
            "status": "success",
            "message": "No new reviews found in this batch.",
            "new_reviews_added": 0,
            "current_total_in_db": existing_count,
            "batch_limit": 300,
        }

    # 4) Insert new reviews with duplicate check on (company_id, google_review_id)
    new_count = 0
    skipped_dupes = 0
    parse_errors = 0

    for item in scraped_data:
        try:
            review_id = (item.get("review_id") or "").strip()
            if not review_id:
                parse_errors += 1
                continue

            # Duplicate check against google_review_id
            stmt = select(Review).where(and_(
                Review.company_id == company_id,
                Review.google_review_id == review_id
            ))
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                skipped_dupes += 1
                continue

            # Sentiment
            text = item.get("text", "") or ""
            try:
                score = analyzer.polarity_scores(text)["compound"]
            except Exception:
                # If analyzer ever fails, default neutral
                score = 0.0
            label = "Positive" if score > 0.05 else "Negative" if score < -0.05 else "Neutral"

            # Time parsing
            google_review_time = _safe_parse_iso(item.get("google_review_time", ""))

            new_review = Review(
                company_id=company_id,
                google_review_id=review_id,
                author_name=item.get("author_name", "Google User") or "Google User",
                rating=int(item.get("rating", 0) or 0),
                text=text,
                google_review_time=google_review_time,
                sentiment_score=score,
                sentiment_label=label,
                source_platform="Google",
            )

            session.add(new_review)
            new_count += 1
        except Exception as e:
            # Keep processing remaining items
            parse_errors += 1
            logger.debug(f"[reviews.ingest] Skipped a malformed review item: {e}")
            continue

    await session.commit()

    if parse_errors or skipped_dupes:
        logger.info(
            f"[reviews.ingest] Company={company.id} new={new_count}, dupes={skipped_dupes}, parse_errors={parse_errors}"
        )

    return {
        "status": "success",
        "new_reviews_added": new_count,
        "current_total_in_db": existing_count + new_count,
        "batch_limit": 300,
    }
