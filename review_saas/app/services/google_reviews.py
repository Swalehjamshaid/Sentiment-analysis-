# filename: app/services/google_reviews.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import hashlib
import googlemaps  # type: ignore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import Company, Review
from app.services.sentiment import score as get_sentiment_score
from app.core.config import settings

def _client() -> 'googlemaps.Client':
    # Using PLACES_API_KEY as the primary key for consistency with your other files
    api_key = settings.GOOGLE_PLACES_API_KEY or settings.GOOGLE_MAPS_API_KEY
    if not api_key:
        raise RuntimeError('GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY missing')
    return googlemaps.Client(key=api_key)

def fetch_place_details(place_id: str) -> Dict[str, Any]:
    gm = _client()
    # Adding fields parameter to ensure reviews are specifically requested
    return gm.place(place_id=place_id, fields=['name', 'rating', 'reviews', 'user_ratings_total'])

def _make_source_id(r: Dict[str, Any]) -> str:
    # Generates a unique hash to prevent duplicate reviews
    base = f"{r.get('author_name','')}-{r.get('time','')}-{r.get('rating','')}-{(r.get('text') or '')[:50]}"
    return hashlib.sha1(base.encode('utf-8', errors='ignore')).hexdigest()

def _parse_review_time(r: Dict[str, Any]) -> Optional[datetime]:
    t = r.get('time')
    if t is None: return None
    try: return datetime.fromtimestamp(int(t), tz=timezone.utc)
    except Exception: return None

def _get_sentiment_label(score: float) -> str:
    # Classification logic as defined in your requirements
    if score >= 0.05: return "positive"
    if score <= -0.05: return "negative"
    return "neutral"

def extract_reviews(details: Dict[str, Any]) -> List[Dict[str, Any]]:
    return (details.get('result') or {}).get('reviews') or []

async def ingest_company_reviews(session: AsyncSession, company: Company) -> Dict[str, Any]:
    if not company.place_id:
        return {"ingested": 0, "skipped": 0, "reason": "no place_id"}
    
    try:
        details = fetch_place_details(company.place_id)
    except Exception as e:
        return {"ingested": 0, "skipped": 0, "error": str(e)}

    items = extract_reviews(details)

    # Update company snapshot attributes
    result = details.get('result') or {}
    company.avg_rating = result.get('rating')
    company.review_count = result.get('user_ratings_total')
    company.last_updated = datetime.now(tz=timezone.utc)

    ingested = 0; skipped = 0
    for r in items:
        sid = _make_source_id(r)
        
        # Check for existing review to prevent duplicates
        stmt = select(Review.id).where(Review.company_id == company.id, Review.source_id == sid)
        exists = (await session.execute(stmt)).scalar_one_or_none()
        
        if exists: 
            skipped += 1
            continue
            
        # Calculate sentiment
        text_content = r.get('text') or ''
        score = get_sentiment_score(text_content)
        label = _get_sentiment_label(score)

        # FIXED: Mapping attributes correctly to match your models.py
        review = Review(
            company_id=company.id,
            source_id=sid,
            author_name=r.get('author_name'),
            rating=r.get('rating'),
            text=text_content,
            review_time=_parse_review_time(r),
            sentiment_score=score,    # Matches models.py
            sentiment_label=label      # Matches models.py
        )
        session.add(review)
        ingested += 1
    
    await session.commit()
    return {"ingested": ingested, "skipped": skipped}
