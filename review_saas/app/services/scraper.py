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
# 🔥 SAFE PARSER (RESILIENT - 2026 PRO LEVEL)
# =====================================================

def find_reviews(obj):
    """Recursively find review-like structures"""
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, list) and len(item) >= 4:
                yield item
            yield from find_reviews(item)


def parse_google_reviews(raw_text: str) -> List[Dict]:

    results = []

    try:
        if raw_text.startswith(")]}'"):
            raw_text = raw_text[4:]

        data = json.loads(raw_text)

        for r in find_reviews(data):
            try:
                review_id = r[0] if isinstance(r[0], str) else None

                author = None
                if len(r) > 1 and isinstance(r[1], list):
                    author = r[1][0]

                rating = None
                if len(r) > 4 and isinstance(r[4], (int, float)):
                    rating = int(r[4])

                text = None
                if len(r) > 3 and isinstance(r[3], str):
                    text = r[3]

                if review_id and text:
                    results.append({
                        "review_id": review_id,
                        "author_name": author or "Anonymous",
                        "rating": rating,
                        "text": clean_text(text),
                        "source": "API"
                    })

            except:
                continue

    except Exception as e:
        logger.warning(f"API parse failed: {e}")

    return results


# =====================================================
# 🧠 HUMAN DELAY
# =====================================================

async def human_delay(a=1.2, b=2.5):
    await asyncio.sleep(random.uniform(a, b))


# =====================================================
# 🔁 SINGLE SESSION
# =====================================================

async def scrape_session(place_id: str, limit: int):

    results = {}
    api_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 2000}
        )

        page = await context.new_page()

        # 🔥 CAPTURE API RESPONSES
        async def handle_response(response):
            try:
                if "listentitiesreviews" in response.url:
                    text = await response.text()
                    parsed = parse_google_reviews(text)

                    for r in parsed:
                        api_results.append(r)

            except:
                pass

        page.on("response", handle_response)

        # 🌍 OPEN MAPS
        await page.goto(f"https://www.google.com/maps/place/?q=place_id:{place_id}", timeout=60000)
        await human_delay()

        # ⭐ OPEN REVIEWS PANEL
        try:
            await page.click('button[jsaction*="pane.reviewChart.moreReviews"]', timeout=10000)
        except:
            try:
                await page.click('button:has-text("reviews")')
            except:
                logger.error("❌ Cannot open reviews panel")
                await browser.close()
                return []

        await human_delay()

        # 📜 SCROLL CONTAINER
        await page.wait_for_selector('div[role="feed"]', timeout=15000)
        scrollable = page.locator('div[role="feed"]')

        last_count = 0
        stagnation = 0

        while len(results) < limit:

            # 🔽 SCROLL
            await scrollable.evaluate("el => el.scrollBy(0, 5000)")
            await human_delay()

            # 🔽 EXPAND TEXT
            buttons = page.locator('button.w8nwRe')
            for i in range(await buttons.count()):
                try:
                    await buttons.nth(i).click()
                except:
                    pass

            # 🧩 DOM EXTRACTION
            cards = await page.query_selector_all('div[data-review-id]')

            for c in cards:
                try:
                    rid = await c.get_attribute("data-review-id")

                    if not rid or rid in results:
                        continue

                    author = await c.locator('.d4r55').inner_text(timeout=2000)
                    text = await (
                        c.locator('.wiI7pd').inner_text(timeout=2000)
                        or c.locator('.bN97Pc').inner_text(timeout=2000)
                    )

                    rating_raw = await c.locator('span.kvMYJc').get_attribute("aria-label")
                    rating = int(rating_raw[0]) if rating_raw else None

                    if text:
                        results[rid] = {
                            "review_id": rid,
                            "author_name": author,
                            "rating": rating,
                            "text": clean_text(text),
                            "source": "DOM"
                        }

                    if len(results) >= limit:
                        break

                except:
                    continue

            logger.info(f"Collected: {len(results)}")

            # 🛑 STOP CONDITION
            if len(results) == last_count:
                stagnation += 1
            else:
                stagnation = 0

            if stagnation >= 5:
                break

            last_count = len(results)

        await browser.close()

    # 🔥 MERGE API DATA
    for r in api_results:
        results[r["review_id"]] = r

    return list(results.values())[:limit]


# =====================================================
# 🚀 MULTI-SESSION ENGINE
# =====================================================

async def fetch_reviews(place_id: str, limit: int = 1000, sessions: int = 3):

    final_results = {}

    tasks = [
        scrape_session(place_id, limit)
        for _ in range(sessions)
    ]

    session_results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in session_results:
        if isinstance(res, Exception):
            logger.warning(f"Session error: {res}")
            continue

        for r in res:
            final_results[r["review_id"]] = r

    logger.info(f"🎯 FINAL UNIQUE REVIEWS: {len(final_results)}")

    return list(final_results.values())[:limit]
