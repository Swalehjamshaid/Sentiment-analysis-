import logging
import random
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

from playwright.async_api import async_playwright

logger = logging.getLogger("scraper")

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 Chrome/122 Mobile",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
]

# =====================================================
# 🧹 CLEAN TEXT
# =====================================================

def clean_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.split())


# =====================================================
# 🧠 HUMAN BEHAVIOR
# =====================================================

async def human_delay():
    await asyncio.sleep(random.uniform(1.2, 3.5))


async def human_mouse(page):
    try:
        await page.mouse.move(random.randint(100, 800), random.randint(100, 800))
    except:
        pass


# =====================================================
# 🔁 SINGLE SESSION SCRAPER
# =====================================================

async def scrape_session(place_id: str, limit: int):

    results = []
    seen_ids = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": random.randint(1200, 1600), "height": random.randint(1800, 2200)}
        )

        page = await context.new_page()

        await page.goto(f"https://www.google.com/maps/place/?q=place_id:{place_id}", timeout=60000)
        await human_delay()

        # Open reviews panel
        try:
            await page.click('button[jsaction*="pane.reviewChart.moreReviews"]', timeout=10000)
        except:
            try:
                await page.click('button:has-text("reviews")')
            except:
                logger.error("❌ Cannot open reviews")
                await browser.close()
                return []

        await human_delay()

        await page.wait_for_selector('div[role="feed"]', timeout=15000)
        scrollable = page.locator('div[role="feed"]')

        last_count = 0
        stagnation = 0

        while len(results) < limit:

            # Scroll
            await scrollable.evaluate("el => el.scrollBy(0, 4000)")
            await human_delay()
            await human_mouse(page)

            # Expand "More"
            more_buttons = page.locator('button.w8nwRe')
            for i in range(await more_buttons.count()):
                try:
                    await more_buttons.nth(i).click()
                except:
                    pass

            cards = await page.query_selector_all('div[data-review-id]')

            for c in cards:
                try:
                    rid = await c.get_attribute("data-review-id")

                    if not rid or rid in seen_ids:
                        continue

                    seen_ids.add(rid)

                    # ⭐ Rating
                    rating_el = await c.query_selector('span.kvMYJc')
                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else None
                    rating = int(rating_raw[0]) if rating_raw else None

                    # 👤 Author
                    author_el = await c.query_selector('.d4r55')
                    author = await author_el.inner_text() if author_el else "Anonymous"

                    # 📝 Text
                    text_el = await c.query_selector('.wiI7pd') or await c.query_selector('.bN97Pc')
                    text = await text_el.inner_text() if text_el else ""

                    text = clean_text(text)

                    if not text:
                        continue

                    results.append({
                        "review_id": rid,
                        "author_name": author,
                        "rating": rating,
                        "text": text,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

                except:
                    continue

            logger.info(f"Session collected: {len(results)}")

            # Stop condition
            if len(results) == last_count:
                stagnation += 1
            else:
                stagnation = 0

            if stagnation >= 6:
                break

            last_count = len(results)

        await browser.close()

    return results


# =====================================================
# 🚀 MAIN MULTI-RUN ENGINE (KEY PART)
# =====================================================

async def fetch_reviews(place_id: str, limit: int = 5000):

    all_results = {}
    sessions = 3   # 🔥 KEY: multiple runs

    for i in range(sessions):
        logger.info(f"🚀 Starting session {i+1}")

        try:
            session_data = await scrape_session(place_id, limit)

            for r in session_data:
                all_results[r["review_id"]] = r

        except Exception as e:
            logger.warning(f"Session {i+1} failed: {e}")

    final_results = list(all_results.values())

    logger.info(f"🎯 FINAL UNIQUE REVIEWS: {len(final_results)}")

    return final_results[:limit]
