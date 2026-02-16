from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import AsyncSessionLocal
from .. import models, schemas
from .deps import get_current_user
from ..services.google_reviews import fetch_places_reviews
from ..services.sentiment import classify_sentiment, extract_keywords
from ..services.reply_generator import generate_reply

router = APIRouter(prefix="/reviews", tags=["reviews"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.post("/fetch/{company_id}")
async def fetch_reviews(company_id: int, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    q = await db.execute(select(models.Company).where(models.Company.id == company_id, models.Company.user_id == user.id))
    company = q.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if not company.google_place_id:
        raise HTTPException(status_code=400, detail="Google Place ID required")
    items = fetch_places_reviews(company.google_place_id)
    added = 0
    for it in items:
        # simple duplicate avoidance by text+date
        existing_q = await db.execute(select(models.Review).where(models.Review.company_id==company.id, models.Review.review_text==it["review_text"], models.Review.review_date==it["review_date"]))
        if existing_q.scalar_one_or_none():
            continue
        sentiment = classify_sentiment(it.get("star_rating"))
        keywords = extract_keywords(it.get("review_text"))
        rv = models.Review(
            company_id=company.id,
            review_text=it.get("review_text"),
            star_rating=it.get("star_rating"),
            review_date=it.get("review_date"),
            reviewer_name=it.get("reviewer_name"),
            sentiment=sentiment,
            keywords=keywords,
        )
        db.add(rv)
        await db.flush()
        # suggested reply
        rep = models.Reply(
            review_id=rv.id,
            suggested_reply=generate_reply(sentiment, rv.reviewer_name, company.contact_email, company.contact_phone),
        )
        db.add(rep)
        added += 1
    await db.commit()
    return {"status": "ok", "added": added}

@router.get("/company/{company_id}", response_model=list[schemas.ReviewOut])
async def list_reviews(company_id: int, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    q = await db.execute(select(models.Review).where(models.Review.company_id == company_id))
    return [r for r in q.scalars().all()]