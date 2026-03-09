# filename: app/services/google_reviews.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

# --- DATABASE INTEGRATION ---
from sqlalchemy import select, and_
from app.core.db import get_session
from app.core.models import Review 
# ----------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ReviewData:
    review_id: str
    author_name: str
    rating: float
    text: str
    time_created: datetime
    sentiment: Optional[str] = None  # positive/neutral/negative
    review_title: Optional[str] = None
    helpful_votes: Optional[int] = 0
    source_platform: Optional[str] = None  # e.g., Google, Yelp
    competitor_name: Optional[str] = None
    additional_fields: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CompanyReviews:
    company_id: str
    reviews: List[ReviewData] = field(default_factory=list)

    def add_review(self, review: ReviewData):
        self.reviews.append(review)

    def rating_summary(self) -> Dict[str, float]:
        """Return average, min, max, and count of ratings."""
        if not self.reviews:
            return {"average": 0.0, "min": 0.0, "max": 0.0, "count": 0}
        ratings = [float(r.rating or 0.0) for r in self.reviews]
        return {
            "average": sum(ratings) / len(ratings),
            "min": min(ratings),
            "max": max(ratings),
            "count": len(ratings),
        }

    def rating_distribution(self) -> Dict[int, int]:
        """Return count of each rating 1..5."""
        def as_star(v: float) -> int:
            try:
                s = int(round(float(v)))
            except Exception:
                s = 0
            return max(1, min(5, s)) if s else 0

        dist = Counter(as_star(r.rating) for r in self.reviews if r.rating is not None)
        return {i: dist.get(i, 0) for i in range(1, 6)}

# ──────────────────────────────────────────────────────────────────────────────
# Service Layer
# ──────────────────────────────────────────────────────────────────────────────

class OutscraperReviewsService:
    """
    Fetch reviews from Outscraper/Google via an injected api_client.
    """
    PAGE_SIZE = 100

    def __init__(self, api_client: Any, *, default_kwargs: Optional[Dict[str, Any]] = None):
        self.client = api_client
        self.default_kwargs = default_kwargs or {}

    @staticmethod
    def _normalize_bounds(start_date: Optional[datetime], end_date: Optional[datetime]) -> Tuple[Optional[datetime], Optional[datetime]]:
        s, e = start_date, end_date
        if s and s.tzinfo: s = s.replace(tzinfo=None)
        if e and e.tzinfo: e = e.replace(tzinfo=None)
        if s: s = datetime.combine(s.date(), time.min)
        if e: e = datetime.combine(e.date(), time.max)
        return s, e

    @staticmethod
    def _coerce_datetime(value: Any) -> Optional[datetime]:
        if value is None: return None
        if isinstance(value, (int, float)):
            try: return datetime.fromtimestamp(float(value))
            except Exception: pass
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.replace(tzinfo=None) if dt.tzinfo else dt
            except Exception: pass
            try: return datetime.strptime(value, "%Y-%m-%d")
            except Exception: pass
        return None

    @staticmethod
    def _first(*vals: Any) -> Any:
        for v in vals:
            if v is not None and not (isinstance(v, str) and v.strip() == ""):
                return v
        return None

    @staticmethod
    def _as_float(val: Any, default: float = 0.0) -> float:
        try: return float(val)
        except Exception: return default

    def _to_review(self, row: Dict[str, Any], *, competitor_name: Optional[str] = None) -> Optional[ReviewData]:
        time_val = self._first(row.get("time"), row.get("timestamp"), row.get("date"), row.get("published_at"))
        time_created = self._coerce_datetime(time_val) or datetime.now()
        
        rating = self._first(row.get("rating"), row.get("stars"), row.get("review_rating"))
        rating_f = self._as_float(rating, default=0.0)
        
        author = self._first(row.get("author_name"), row.get("author"), row.get("user_name")) or "Anonymous"
        review_id = self._first(row.get("review_id"), row.get("id"), row.get("google_review_id"))
        
        if not review_id:
            review_id = f"noid-{hash((author, time_created.isoformat(), rating_f))}"

        text = self._first(row.get("text"), row.get("review_text"), row.get("content")) or ""
        title = self._first(row.get("title"), row.get("review_title"), row.get("summary"))
        helpful = self._first(row.get("helpful_votes"), row.get("likes"), row.get("votes"))
        platform = self._first(row.get("platform"), row.get("source")) or "Google"
        
        entity_name = competitor_name or self._first(row.get("competitor_name"), row.get("place_name"))

        return ReviewData(
            review_id=str(review_id),
            author_name=str(author),
            rating=rating_f,
            text=str(text),
            time_created=time_created,
            sentiment=row.get("sentiment"),
            review_title=str(title) if title else None,
            helpful_votes=int(self._as_float(helpful, 0.0)),
            source_platform=str(platform),
            competitor_name=str(entity_name) if entity_name else None,
            additional_fields=row,
        )

    async def fetch_reviews(self, place_id: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, max_reviews: Optional[int] = None, *, competitor_name: Optional[str] = None, **extra_kwargs: Any) -> List[ReviewData]:
        all_reviews: List[ReviewData] = []
        offset = 0
        start_norm, end_norm = self._normalize_bounds(start_date, end_date)
        
        while True:
            kwargs = {**self.default_kwargs, **extra_kwargs}
            # Ensure we await the async client call
            response = await self.client.get_reviews(place_id=place_id, limit=self.PAGE_SIZE, offset=offset, **kwargs)
            raw = response.get("reviews", []) or []
            if not raw: break
            
            for row in raw:
                rd = self._to_review(row, competitor_name=competitor_name)
                if not rd: continue
                if start_norm and rd.time_created < start_norm: continue
                if end_norm and rd.time_created > end_norm: continue
                
                all_reviews.append(rd)
                if max_reviews and len(all_reviews) >= max_reviews: break
            
            if (max_reviews and len(all_reviews) >= max_reviews) or len(raw) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE
        return all_reviews

    async def fetch_many(self, entities: List[Dict[str, Any] | str], start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, max_reviews_per_entity: Optional[int] = None, **extra_kwargs: Any) -> Dict[str, List[ReviewData]]:
        results: Dict[str, List[ReviewData]] = {}
        for ent in entities:
            if isinstance(ent, str):
                pid, name = ent, None
            elif isinstance(ent, dict):
                pid = str(ent.get("place_id") or "").strip()
                name = ent.get("name") or ent.get("competitor_name")
            else: continue
            if not pid: continue
            
            results[pid] = await self.fetch_reviews(place_id=pid, start_date=start_date, end_date=end_date, max_reviews=max_reviews_per_entity, competitor_name=name, **extra_kwargs)
        return results

# ──────────────────────────────────────────────────────────────────────────────
# DATABASE PERSISTENCE LAYER (THE SYNC ENGINE)
# ──────────────────────────────────────────────────────────────────────────────

async def run_batch_review_ingestion(api_client: Any, primary_company_id: int, entities: List[Dict[str, Any] | str], start_date: Optional[datetime] = None):
    """
    Core engine to fetch from API and save to PostgreSQL.
    """
    logger.info(f"🚀 Starting Sync for Company ID: {primary_company_id}")
    service = OutscraperReviewsService(api_client)
    
    # 1. Fetch data
    grouped_data = await service.fetch_many(
        entities=entities, 
        start_date=start_date, 
        max_reviews_per_entity=500
    )

    # 2. Persist to Database
    async with get_session() as session:
        total_saved = 0
        for place_id, reviews in grouped_data.items():
            for rd in reviews:
                # Duplicate Check using google_review_id
                stmt = select(Review).where(and_(
                    Review.company_id == primary_company_id,
                    Review.google_review_id == rd.review_id
                ))
                res = await session.execute(stmt)
                if res.scalar_one_or_none():
                    continue

                # Create Review instance
                new_review = Review(
                    company_id=primary_company_id,
                    google_review_id=rd.review_id,
                    author_name=rd.author_name,
                    rating=rd.rating,
                    text=rd.text,
                    google_review_time=rd.time_created,
                    competitor_name=rd.competitor_name,
                    source_platform=rd.source_platform or "Google"
                )
                session.add(new_review)
                total_saved += 1
        
        if total_saved > 0:
            await session.commit()
            logger.info(f"✅ Sync Complete: {total_saved} reviews saved to DB.")
        else:
            logger.info("ℹ️ No new reviews found.")
