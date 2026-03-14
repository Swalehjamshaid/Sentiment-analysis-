# filename: google_reviews_service.py
from __future__ import annotations

import os
import logging
import hashlib
import httpx
import asyncio
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Union, Iterable
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, UniqueConstraint, and_, cast, Date, desc, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from pydantic import BaseModel

# ---------------------------------------------------------
# 1. LOGGING & CONFIGURATION
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("app.google_reviews")

# Environment variables for production-readiness
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/reviews_db")
GOOGLE_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "AIzaSyDjQFzX3Wak4maUWhSXstPmnbBOOKGVGfc")
HTTPX_TIMEOUT = 30.0

# ---------------------------------------------------------
# 2. DATABASE SCHEMA (models.py)
# ---------------------------------------------------------
Base = declarative_base()

class Company(Base):
    """
    Represents a business entity registered in the system.
    """
    __tablename__ = "companies"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(1000))
    google_place_id: Mapped[str | None] = mapped_column(String(512), unique=True, index=True)
    
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")

class Review(Base):
    """
    Persisted review records retrieved from Google/Outscraper.
    Unique constraint on company + google_review_id prevents duplicates.
    """
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("company_id", "google_review_id", name="_company_review_uc"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    google_review_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    author_name: Mapped[str | None] = mapped_column(String(255))
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    text: Mapped[str | None] = mapped_column(Text)
    google_review_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    profile_photo_url: Mapped[str | None] = mapped_column(String(1000))
    
    company = relationship("Company", back_populates="reviews")

# ---------------------------------------------------------
# 3. DATABASE SESSION MANAGEMENT (db.py)
# ---------------------------------------------------------
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def get_session():
    """Dependency for providing database sessions to routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# ---------------------------------------------------------
# 4. NORMALIZATION & ANALYTICS SERVICE (google_reviews.py)
# ---------------------------------------------------------
class OutscraperReviewsService:
    """
    Handles data transformation from raw scraper responses to 
    standardized database objects.
    """
    @staticmethod
    def _coerce_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        try:
            if isinstance(value, (int, float)):
                # Handle milliseconds vs seconds
                if value > 10_000_000_000:
                    return datetime.utcfromtimestamp(value / 1000.0)
                return datetime.utcfromtimestamp(value)
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            pass
        return datetime.utcnow()

    @staticmethod
    def _calculate_sentiment(rating: float) -> float:
        """Simple mapping of 1-5 stars to -1.0 to 1.0 sentiment score."""
        r = max(1.0, min(5.0, float(rating)))
        return round((r - 3.0) / 2.0, 2)

    def normalize(self, raw: Dict[str, Any], company_id: int) -> Dict[str, Any]:
        """Normalizes heterogeneous keys from different scraper versions."""
        rating = float(raw.get("review_rating") or raw.get("rating") or 0.0)
        ts_val = raw.get("review_timestamp") or raw.get("time") or raw.get("review_datetime_utc")
        
        return {
            "company_id": company_id,
            "google_review_id": str(raw.get("review_id") or raw.get("google_review_id")),
            "author_name": str(raw.get("author_title") or raw.get("author_name") or "Anonymous"),
            "rating": rating,
            "text": str(raw.get("review_text") or raw.get("text") or ""),
            "google_review_time": self._coerce_datetime(ts_val),
            "sentiment_score": float(raw.get("sentiment_score") or self._calculate_sentiment(rating)),
            "profile_photo_url": str(raw.get("author_image") or raw.get("profile_photo_url") or "")
        }

async def run_batch_review_ingestion(client: Any, entities: List[Company], start: datetime, end: datetime):
    """
    Main ingestion engine. Orchestrates fetching, deduplication, and persistence.
    """
    service = OutscraperReviewsService()
    total_saved = 0
    
    for company in entities:
        logger.info(f"Syncing company: {company.name} (Place ID: {company.google_place_id})")
        
        # Real-world Outscraper client call happens here
        try:
            raw_data = await client.fetch_reviews(company)
        except Exception as e:
            logger.error(f"Failed fetching reviews for {company.name}: {e}")
            continue

        async with AsyncSessionLocal() as session:
            for raw in raw_data:
                norm = service.normalize(raw, company.id)
                
                # Filter by logical window (Scenario 1 & 2)
                if not (start <= norm["google_review_time"] <= end):
                    continue

                # Check for existing record to prevent UniqueConstraint violations
                exists_stmt = select(Review.id).where(
                    and_(Review.company_id == company.id, Review.google_review_id == norm["google_review_id"])
                )
                result = await session.execute(exists_stmt)
                if result.first():
                    continue

                session.add(Review(**norm))
                total_saved += 1
            
            await session.commit()
            
    return {"total_saved": total_saved}

# ---------------------------------------------------------
# 5. API ROUTES (reviews.py)
# ---------------------------------------------------------
router = APIRouter(tags=["Reviews"])

@asynccontextmanager
async def _httpx_client():
    async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
        yield client

def _resolve_date_range(start: Optional[str], end: Optional[str]):
    """
    Scenario 1: No dates -> Last 15 days.
    Scenario 2: Range provided -> Exact window.
    """
    try:
        e_dt = datetime.strptime(end, "%Y-%m-%d").date() if end else date.today()
        if start:
            s_dt = datetime.strptime(start, "%Y-%m-%d").date()
        else:
            s_dt = e_dt - timedelta(days=14)
        return s_dt, e_dt
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be in YYYY-MM-DD format")

@router.get("/api/google_autocomplete")
async def google_autocomplete(input: str):
    """Proxy for Google Places Autocomplete SDK."""
    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {"input": input, "key": GOOGLE_API_KEY}
    async with _httpx_client() as client:
        r = await client.get(url, params=params)
        return r.json()

@router.get("/api/reviews")
async def get_dashboard_reviews(
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session)
):
    """Retrieves analytics-ready reviews from PostgreSQL."""
    s_date, e_date = _resolve_date_range(start, end)
    
    stmt = (
        select(Review)
        .where(
            and_(
                Review.company_id == company_id,
                cast(Review.google_review_time, Date) >= s_date,
                cast(Review.google_review_time, Date) <= e_date
            )
        )
        .order_by(desc(Review.google_review_time))
        .limit(limit)
    )
    
    result = await session.execute(stmt)
    rows = result.scalars().all()
    
    return {
        "feed": [
            {
                "author_name": r.author_name,
                "rating": r.rating,
                "sentiment_score": r.sentiment_score,
                "review_time": r.google_review_time.date().isoformat(),
                "text": r.text
            } for r in rows
        ],
        "count": len(rows)
    }

@router.post("/api/reviews/ingest/{company_id}")
async def sync_company_reviews(
    request: Request,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    """Triggers external sync and persists to database."""
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    client = getattr(request.app.state, "reviews_client", None)
    s_date, e_date = _resolve_date_range(start, end)
    
    summary = await run_batch_review_ingestion(
        client=client,
        entities=[company],
        start=datetime.combine(s_date, datetime.min.time()),
        end=datetime.combine(e_date, datetime.max.time())
    )
    
    return {"status": "success", "total_added": summary["total_saved"]}

# ---------------------------------------------------------
# 6. MAIN APP INITIALIZATION
# ---------------------------------------------------------
app = FastAPI(title="Review SaaS Backend")
app.include_router(router)

class MockOutscraperClient:
    """Mock client used to demonstrate structure without valid API keys."""
    async def fetch_reviews(self, company: Company):
        # Simulated return data from Outscraper
        return [
            {
                "review_id": f"rev_{hash(company.google_place_id)}_{i}",
                "author_name": f"User {i}",
                "rating": 4.0 if i % 2 == 0 else 2.0,
                "text": "Simulated review content",
                "time": datetime.utcnow().timestamp() - (i * 86400)
            } for i in range(5)
        ]

@app.on_event("startup")
async def startup_event():
    """Initializes external clients and database tables."""
    app.state.reviews_client = MockOutscraperClient()
    async with engine.begin() as conn:
        # Warning: In production use Alembic migrations instead
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Application started and database initialized.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
