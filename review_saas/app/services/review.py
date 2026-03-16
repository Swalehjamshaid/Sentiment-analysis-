# filename: app/services/review.py

from __future__ import annotations
import logging
import asyncio
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert

from app.core.config import settings
from app.core.models import Review

# We use a localized signal registry to avoid circular imports with app.routes.reviews
# This ensures uvicorn can load the app without the "importlib" crash.
cancel_requests: Set[int] = set()

logger = logging.getLogger(__name__)

class OutscraperReviewsClient:
    def __init__(self, *, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.OUTSCRAPER_BASE_URL).rstrip("/")
        self.api_key = (api_key or settings.OUTSCRAPER_API_KEY).strip()
        self.reviews_endpoint = f"{self.base_url}/maps/reviews-v3"

    async def fetch_batch(self, client: httpx.AsyncClient, query: str, limit: int, skip: int) -> List[Dict[str, Any]]:
        params = {
            "query": query,
            "reviewsLimit": limit,
            "skip": skip,
            "async": "false",
            "ignoreEmpty": "true"
        }
        headers = {"X-API-KEY": self.api_key}
        try:
            # Fast connection timeout, long read timeout for deep Google Maps scraping
            response = await client.get(self.reviews_endpoint, params=params, headers=headers)
            response.raise_for_status()
            data = response.json().get("data", [])
            return data[0].get("reviews_data", []) if data else []
        except Exception as e:
            logger.error(f"Batch fail at skip {skip}: {str(e)}")
            return []

async def ingest_outscraper_reviews(company_obj: Any, session: AsyncSession, max_reviews: int = 10000) -> int:
    """
    HIGH-SPEED PARALLEL INGESTION:
    Utilizes a Producer-Consumer pattern to fetch from Google and save to DB 
    at maximum possible throughput.
    """
    client_wrapper = OutscraperReviewsClient()
    query = getattr(company_obj, "google_place_id", None) or getattr(company_obj, "name", None)

    # 1. In-Memory ID Loading for O(1) duplicate checking
    stmt = select(Review.google_review_id).where(Review.company_id == company_obj.id)
    result = await session.execute(stmt)
    existing_ids = set(result.scalars().all())

    batch_size = 250
    # Process 10 bags of reviews simultaneously
    fetch_concurrency = 10  
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    total_new = 0
    
    # Semaphore protects against API rate limits and memory spikes
    fetch_sem = asyncio.Semaphore(fetch_concurrency)

    async def fetch_worker(client: httpx.AsyncClient, skip: int):
        """Producer worker: Fired in parallel to saturate network bandwidth"""
        if company_obj.id in cancel_requests:
            return

        async with fetch_sem:
            batch = await client_wrapper.fetch_batch(client, query, batch_size, skip)
            if batch:
                await queue.put(batch)

    async def producer():
        """Coordinator: Triggers all parallel fetch workers"""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, read=300.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
        ) as client:
            tasks = []
            for skip in range(0, max_reviews, batch_size):
                if company_obj.id in cancel_requests:
                    logger.info(f"🛑 Manual stop triggered for {company_obj.name}")
                    break
                
                tasks.append(asyncio.create_task(fetch_worker(client, skip)))
            
            # Fire all requests concurrently
            await asyncio.gather(*tasks)

        # Signal consumer that production is finished
        await queue.put(None)

    async def consumer():
        """Database worker: Performs bulk inserts for maximum DB speed"""
        nonlocal total_new
        while True:
            batch = await queue.get()
            if batch is None:
                queue.task_done()
                break

            to_insert = []
            for raw in batch:
                rid = raw.get("review_id")
                if not rid or rid in existing_ids:
                    continue

                dt_obj = None
                raw_ts = raw.get("review_datetime_utc")
                if raw_ts:
                    try:
                        dt_obj = datetime.strptime(raw_ts, "%m/%d/%Y %H:%M:%S")
                    except: 
                        pass

                to_insert.append({
                    "company_id": company_obj.id,
                    "google_review_id": rid,
                    "author_name": raw.get("author_title"),
                    "rating": raw.get("review_rating"),
                    "text": raw.get("review_text"),
                    "google_review_time": dt_obj,
                    "source_platform": "Google"
                })
                existing_ids.add(rid)

            if to_insert:
                # SQLAlchemy Core insert() is 50-100x faster than session.add()
                await session.execute(insert(Review), to_insert)
                await session.commit()
                total_new += len(to_insert)
            
            queue.task_done()

    # Execute Producer and Consumer concurrently
    await asyncio.gather(producer(), asyncio.create_task(consumer()))

    # Cleanup stop signal
    if company_obj.id in cancel_requests:
        cancel_requests.remove(company_obj.id)

    logger.info(f"✅ Turbo Ingested {total_new} new reviews for {company_obj.name}")
    return total_new
