# filename: review_saas/app/services/scraper.py

import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any
import asyncpg
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


# PostgreSQL Config (update these with your actual DB credentials)
DB_CONFIG = {
    "user": "postgres",
    "password": "password",
    "database": "reviews_db",
    "host": "localhost",
    "port": 5432
}


async def save_reviews_to_db(company_id: int, reviews: List[Dict[str, Any]]):
    """
    Save reviews to Postgres with upsert to avoid duplicates
    """
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        for r in reviews:
            await conn.execute("""
                INSERT INTO reviews (review_id, rating, text, author_name, google_review_time, company_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (review_id) DO NOTHING
            """, r["review_id"], r["rating"], r["text"], r["author_name"], r["google_review_time"], company_id)
    except Exception as e:
        logger.error(f"❌ DB Save Error: {e}")
    finally:
        await conn.close()


async def fetch_reviews(place_id: str, company_id: int, batch_size: int = 200, skip: int = 0) -> int:
    """
    Fetch reviews in batches and save to PostgreSQL
    Returns the number of reviews saved
    """
    reviews = []
    place_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 900},
                user_agent="Mozilla/5.0",
                locale="en-US"
            )
            page = await context.new_page()
            logger.info(f"🚀 Opening Place ID: {place_id}")
            await page.goto(place_url, timeout=60000)

            # Open Reviews tab
            try:
                await page.wait_for_selector('button[jsaction*="pane.reviewChart"]', timeout=15000)
                await page.click('button[jsaction*="pane.reviewChart"]')
                logger.info("✅ Reviews tab opened")
            except:
                logger.error("❌ Failed to open Reviews tab")
                await browser.close()
                return 0

            await page.wait_for_selector('div[role="feed"]', timeout=15000)

            # Scroll until enough reviews are visible
            last_count = 0
            total_needed = skip + batch_size
            for i in range(50):  # max scroll loops
                await page.evaluate('''
                    const el = document.querySelector('div[role="feed"]');
                    if (el) el.scrollBy(0, 3000);
                ''')
                await page.wait_for_timeout(1500)
                elements = await page.query_selector_all('div[role="article"]')
                current_count = len(elements)
                logger.info(f"🔄 Scroll Loop {i+1}: Found {current_count} reviews")
                if current_count >= total_needed:
                    break
                if current_count == last_count:
                    break
                last_count = current_count

            # Extract reviews
            final_elements = await page.query_selector_all('div[role="article"]')
            logger.info(f"🧐 Extracting {len(final_elements)} reviews")
            batch_elements = final_elements[skip:skip + batch_size]

            for r in batch_elements:
                try:
                    text_el = await r.query_selector('.wiI7pd')
                    author_el = await r.query_selector('.d4r55')
                    rating_el = await r.query_selector('span[role="img"]')

                    if not author_el:
                        continue

                    text = await text_el.inner_text() if text_el else ""
                    author = await author_el.inner_text()

                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                    rating_match = re.search(r'(\d+)', rating_raw)
                    rating = int(rating_match.group(1)) if rating_match else 0

                    # Unique review ID to avoid duplicates in DB
                    review_id = f"{author}_{hash(text)}"

                    reviews.append({
                        "review_id": review_id,
                        "rating": rating,
                        "text": text,
                        "author_name": author,
                        "google_review_time": datetime.utcnow().isoformat()
                    })
                except Exception as e:
                    logger.debug(f"Row skip: {e}")
                    continue

            await browser.close()
            logger.info(f"✅ Collected {len(reviews)} reviews in this batch.")

            # Save to DB
            await save_reviews_to_db(company_id, reviews)

            return len(reviews)

    except Exception as e:
        logger.error(f"❌ Scraper Critical Failure: {str(e)}")
        return 0


# Example usage:
# await fetch_reviews("ChIJe2LWbaIIGTkRZhr_Fbyvkvs", company_id=1, batch_size=200, skip=0)
# Next batch: skip=200
