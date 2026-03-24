import asyncio
import random
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any

from playwright.async_api import async_playwright

logger = logging.getLogger("scraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/122 Mobile",
]

# =====================================================
# 🧹 CLEAN
# =====================================================

def clean_text(text):
    return " ".join(text.split()) if text else ""

# =====================================================
# 🔥 GOOGLE RESPONSE PARSER (REAL STRUCTURE)
# =====================================================

def parse_google_reviews(raw_text: str) -> List[Dict]:

    results = []

    try:
        # Google wraps JSON in )]}' 
        if raw_text.startswith(")]}'"):
            raw_text = raw_text[4:]

        data = json.loads(raw_text)

        # Deep nested structure (based on real reverse engineering)
        reviews = data[2] if len(data) > 2 else []

        for r in reviews:
            try:
                review_id = r[0]

                author = r[1][0] if r[1] else "Anonymous"
                rating = r[4] if len(r) > 4 else None
                text = r[3] if len(r) > 3 else ""

                results.append({
                    "review_id": review_id,
                    "author_name": author,
                    "rating": rating,
                    "text": clean_text(text),
                    "source": "API"
                })

            except:
                continue

    except:
        pass

    return results

# =====================================================
# 🧠 HUMAN SIMULATION
# =====================================================

async def human_delay():
    await asyncio.sleep(random.uniform(1.2, 3))

# =====================================================
# 🔁 SINGLE SESSION
# =====================================================

async def scrape_session(place_id: str):

    results = {}
    api_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS)
        )

        page = await context.new_page()

        # 🔥 Capture API
        async def handle_response(response):
            try:
                url = response.url

                if "listentitiesreviews" in url:
                    text = await response.text()
                    parsed = parse_google_reviews(text)

                    for r in parsed:
                        api_results.append(r)

            except:
                pass

        page.on("response", handle_response)

        # Open Maps
        await page.goto(f"https://www.google.com/maps/place/?q=place_id:{place_id}")
        await human_delay()

        # Click reviews
        try:
            await page.click('button[jsaction*="pane.reviewChart.moreReviews"]', timeout=10000)
        except:
            await page.click('button:has-text("reviews")')

        await human_delay()

        scrollable = page.locator('div[role="feed"]')

        last_count = 0
        stagnation = 0

        while True:

            await scrollable.evaluate("el => el.scrollBy(0, 4000)")
            await human_delay()

            cards = await page.query_selector_all('div[data-review-id]')

            for c in cards:
                try:
                    rid = await c.get_attribute("data-review-id")
                    if not rid or rid in results:
                        continue

                    author_el = await c.query_selector('.d4r55')
                    author = await author_el.inner_text() if author_el else "Anonymous"

                    text_el = await c.query_selector('.wiI7pd') or await c.query_selector('.bN97Pc')
                    text = await text_el.inner_text() if text_el else ""

                    rating_el = await c.query_selector('span.kvMYJc')
                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else None
                    rating = int(rating_raw[0]) if rating_raw else None

                    if text:
                        results[rid] = {
                            "review_id": rid,
                            "author_name": author,
                            "rating": rating,
                            "text": clean_text(text),
                            "source": "DOM"
                        }

                except:
                    continue

            if len(results) == last_count:
                stagnation += 1
            else:
                stagnation = 0

            if stagnation >= 5:
                break

            last_count = len(results)

        await browser.close()

    # Merge API + DOM
    for r in api_results:
        results[r["review_id"]] = r

    return list(results.values())

# =====================================================
# 🚀 MULTI-SESSION ENGINE (KEY FOR 95%)
# =====================================================

async def fetch_reviews(place_id: str, sessions: int = 3):

    final_results = {}

    for i in range(sessions):
        logger.info(f"🚀 Session {i+1}")

        try:
            session_data = await scrape_session(place_id)

            for r in session_data:
                final_results[r["review_id"]] = r

        except Exception as e:
            logger.warning(f"Session failed: {e}")

    logger.info(f"🎯 FINAL UNIQUE REVIEWS: {len(final_results)}")

    return list(final_results.values())
