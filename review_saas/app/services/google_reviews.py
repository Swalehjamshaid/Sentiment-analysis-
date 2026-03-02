
# filename: app/services/google_reviews.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import hashlib
import googlemaps  # type: ignore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import Company, Review
from app.services.sentiment import score as sentiment_score
from app.core.config import settings


def _client() -> 'googlemaps.Client':
    if not settings.GOOGLE_MAPS_API_KEY:
        raise RuntimeError('GOOGLE_MAPS_API_KEY missing')
    return googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)

def fetch_place_details(place_id: str) -> Dict[str, Any]:
    gm = _client()
    return gm.place(place_id=place_id)

def _make_source_id(r: Dict[str, Any]) -> str:
    base = f"{r.get('author_name','')}-{r.get('time','')}-{r.get('rating','')}-{(r.get('text') or '')[:50]}"
    return hashlib.sha1(base.encode('utf-8', errors='ignore')).hexdigest()

def _parse_review_time(r: Dict[str, Any]) -> Optional[datetime]:
    t = r.get('time')
    if t is None: return None
    try: return datetime.fromtimestamp(int(t), tz=timezone.utc)
    except Exception: return None

def extract_reviews(details: Dict[str, Any]) -> List[Dict[str, Any]]:
    return (details.get('result') or {}).get('reviews') or []

async def ingest_company_reviews(session: AsyncSession, company: Company) -> Dict[str, Any]:
    if not company.place_id:
        return {"ingested": 0, "skipped": 0, "reason": "no place_id"}
    details = fetch_place_details(company.place_id)
    items = extract_reviews(details)

    # update snapshot
    result = details.get('result') or {}
    company.avg_rating = result.get('rating')
    company.review_count = result.get('user_ratings_total')
    company.last_updated = datetime.now(tz=timezone.utc)

    ingested = 0; skipped = 0
    for r in items:
        sid = _make_source_id(r)
        exists = (await session.execute(select(Review.id).where(Review.company_id==company.id, Review.source_id==sid))).scalar_one_or_none()
        if exists: skipped += 1; continue
        review = Review(
            company_id=company.id,
            source_id=sid,
            author_name=r.get('author_name'),
            rating=r.get('rating'),
            text=r.get('text'),
            review_time=_parse_review_time(r),
            sentiment_compound=sentiment_score(r.get('text') or ''),
        )
        session.add(review)
        ingested += 1
    await session.commit()
    return {"ingested": ingested, "skipped": skipped}
