from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional
from app.core.db import get_session
from app.core.models import Review, Company
from pydantic import BaseModel

router = APIRouter()

# --------------------------- Pydantic Schemas ---------------------------
class ReviewCreate(BaseModel):
    company_id: int
    google_review_id: str
    author_name: str
    rating: int
    text: str

class ReviewResponse(BaseModel):
    id: int
    company_id: int
    google_review_id: str
    author_name: str
    rating: int
    text: str

    class Config:
        orm_mode = True

# --------------------------- Ingest Reviews (Batch) ---------------------------
@router.post("/ingest/{batch_id}", response_model=dict)
async def ingest_reviews(batch_id: int, session: AsyncSession = Depends(get_session)):
    """
    Simulates fetching and saving a batch of reviews.
    Replace this logic with real Google API fetch if needed.
    """
    try:
        print(f"Fetching batch {batch_id}...")  # Debug log

        # Example batch of reviews
        new_reviews = [
            Review(
                company_id=1,
                google_review_id=f"rev-{batch_id}-001",
                author_name="John Doe",
                rating=5,
                text="Excellent service!"
            ),
            Review(
                company_id=1,
                google_review_id=f"rev-{batch_id}-002",
                author_name="Jane Doe",
                rating=4,
                text="Good experience!"
            ),
        ]

        session.add_all(new_reviews)
        await session.commit()

        return {"status": "success", "batch_id": batch_id, "count": len(new_reviews)}
    except Exception as ex:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(ex))

# --------------------------- List Reviews ---------------------------
@router.get("/", response_model=List[ReviewResponse])
async def list_reviews(
    company_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session)
):
    try:
        query = select(Review)
        if company_id:
            query = query.where(Review.company_id == company_id)
        result = await session.execute(query)
        reviews = result.scalars().all()
        return reviews
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

# --------------------------- Delete Review ---------------------------
@router.delete("/{review_id}", response_model=dict)
async def delete_review(review_id: int, session: AsyncSession = Depends(get_session)):
    try:
        query = delete(Review).where(Review.id == review_id)
        result = await session.execute(query)
        await session.commit()
        return {"status": "success", "deleted_id": review_id}
    except Exception as ex:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(ex))

# --------------------------- Fetch Single Review ---------------------------
@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(review_id: int, session: AsyncSession = Depends(get_session)):
    try:
        result = await session.execute(select(Review).where(Review.id == review_id))
        review = result.scalars().first()
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        return review
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
