from datetime import datetime
from typing import Optional
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review, Company

router = APIRouter(prefix="/api/reviews")

async def save_reviews_to_db(session: AsyncSession, company_id: str, reviews: list[dict]):
    print(f"DEBUG STEP 4: Inside save_reviews_to_db with {len(reviews)} reviews")
    saved = []
    for r in reviews:
        ext_id = r.get("review_id")
        if not ext_id:
            print("DEBUG: Skipping review - no review_id found")
            continue
            
        existing = await session.execute(
            select(Review).where(Review.google_review_id == ext_id)
        )
        if existing.scalars().first():
            continue

        review_date_str = r.get("review_time")
        try:
            review_date = datetime.fromisoformat(review_date_str.replace("Z", "+00:00")) if review_date_str else datetime.utcnow()
        except:
            review_date = datetime.utcnow()

        new_review = Review(
            company_id=int(company_id),
            google_review_id=ext_id,
            author_name=r.get("author_title") or r.get("author_name", "Anonymous"),
            rating=int(r.get("review_rating") or r.get("rating") or 0),
            text=r.get("review_text") or r.get("text", ""),
            google_review_time=review_date,
            sentiment_score=float(r.get("sentiment_score", 0)),
            source_platform="Google"
        )
        session.add(new_review)
        saved.append(new_review)

    if saved:
        try:
            await session.commit()
            print(f"DEBUG STEP 5: Successfully committed {len(saved)} reviews")
            for r in saved:
                await session.refresh(r)
        except Exception as e:
            await session.rollback()
            print(f"DEBUG ERROR: Commit failed: {e}")
    else:
        print("DEBUG: No new reviews to save (either 0 fetched or all duplicates)")
            
    return saved

@router.get("/")
async def get_reviews(
    request: Request,
    company_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    print(f"DEBUG STEP 1: Request received for company_id {company_id}")
    
    client = getattr(request.app.state, "reviews_client", None)
    if not client:
        print("DEBUG ERROR: Client not found in app.state")
        raise HTTPException(status_code=500, detail="Client not configured")

    result = await session.execute(select(Company).where(Company.id == int(company_id)))
    company = result.scalars().first()
    if not company:
        print(f"DEBUG ERROR: Company {company_id} not found in DB")
        raise HTTPException(status_code=404, detail="Company not found")

    print(f"DEBUG STEP 2: Fetching from Outscraper for Place ID: {company.google_place_id}")
    try:
        raw_reviews = await client.fetch_reviews(company.google_place_id, max_reviews=limit)
        print(f"DEBUG STEP 3: Outscraper returned {len(raw_reviews)} reviews")
    except Exception as e:
        print(f"DEBUG ERROR: Outscraper call failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))

    # Date filtering
    start_date = datetime.fromisoformat(start) if start else None
    end_date = datetime.fromisoformat(end) if end else None
    if start_date or end_date:
        filtered = []
        for r in raw_reviews:
            rt_str = r.get("review_time")
            if not rt_str: continue
            try:
                rt = datetime.fromisoformat(rt_str.split("T")[0])
                if start_date and rt < start_date: continue
                if end_date and rt > end_date: continue
                filtered.append(r)
            except: continue
        raw_reviews = filtered
        print(f"DEBUG STEP 3.1: After filtering, {len(raw_reviews)} reviews remain")

    saved_reviews = await save_reviews_to_db(session, company_id, raw_reviews)

    return {
        "status": "success",
        "count": len(saved_reviews),
        "feed": [
            {
                "google_review_id": r.google_review_id,
                "author_name": r.author_name,
                "text": r.text
            } for r in saved_reviews
        ]
    }
