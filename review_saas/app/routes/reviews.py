from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_session
from app.core import models

# 🔥 Playwright for scraping
from playwright.async_api import async_playwright

router = APIRouter(prefix="/api/reviews", tags=["Reviews"])

logger = logging.getLogger(__name__)


# ---------------------------------------------------
# 🔥 HELPER: Scrape reviews using Playwright
# ---------------------------------------------------
async def scrape_reviews(place_id: str, max_reviews: int = 200):
    reviews = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        await page.goto(url, timeout=60000)

        # Open reviews tab
        await page.wait_for_selector('button[jsaction="pane.reviewChart.moreReviews"]', timeout=15000)
        await page.click('button[jsaction="pane.reviewChart.moreReviews"]')

        await page.wait_for_selector('div[role="article"]')

        last_height = 0

        while len(reviews) < max_reviews:
            cards = await page.query_selector_all('div[role="article"]')

            for card in cards:
                try:
                    text_el = await card.query_selector('span[jsname="bN97Pc"]')
                    text = await text_el.inner_text() if text_el else ""

                    rating_el = await card.query_selector('span[aria-label*="star"]')
                    rating = 0
                    if rating_el:
                        rating_text = await rating_el.get_attribute("aria-label")
                        rating = int(rating_text[0])

                    time_el = await card.query_selector('span.rsqaWe')
                    review_time = datetime.utcnow()  # fallback

                    reviews.append({
                        "google_review_id": hash(text + str(rating)),
                        "text": text,
                        "rating": rating,
                        "time": review_time
                    })

                except Exception:
                    continue

                if len(reviews) >= max_reviews:
                    break

            await page.mouse.wheel(0, 5000)
            await asyncio.sleep(2)

            new_height = len(cards)
            if new_height == last_height:
                break
            last_height = new_height

        await browser.close()

    return reviews


# ---------------------------------------------------
# 🚀 MAIN API: Ingest Reviews
# ---------------------------------------------------
@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_session),
):
    # ✅ Get company (ASYNC FIX)
    result = await db.execute(
        select(models.Company).where(models.Company.id == company_id)
    )
    company = result.scalars().first()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # ✅ FIXED: Use correct field
    if not company.google_place_id:
        raise HTTPException(status_code=400, detail="No Google Place ID found")

    place_id = company.google_place_id

    total_saved = 0
    batch_size = 200
    has_more = True
    page_count = 0

    while has_more:
        page_count += 1
        logger.info(f"Fetching batch {page_count}")

        scraped_reviews = await scrape_reviews(place_id, max_reviews=batch_size)

        if not scraped_reviews:
            break

        for r in scraped_reviews:
            review_time = r["time"]

            # ✅ Date filtering
            if start_date and review_time < start_date:
                has_more = False
                break
            if end_date and review_time > end_date:
                continue

            # ✅ Check duplicate
            existing = await db.execute(
                select(models.Review).where(
                    models.Review.google_review_id == str(r["google_review_id"]),
                    models.Review.company_id == company_id,
                )
            )
            if existing.scalars().first():
                continue

            # ✅ Save review
            new_review = models.Review(
                company_id=company_id,
                google_review_id=str(r["google_review_id"]),
                rating=r["rating"],
                text=r["text"],
                google_review_time=review_time,
                source_platform="Google",
            )

            db.add(new_review)
            total_saved += 1

        await db.commit()

        # Stop if less than batch
        if len(scraped_reviews) < batch_size:
            has_more = False

    return {
        "status": "success",
        "company_id": company_id,
        "reviews_saved": total_saved
    }
