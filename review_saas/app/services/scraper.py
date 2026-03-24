import asyncio
import random
import logging
from typing import List, Dict, Any

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

logger = logging.getLogger("app.scraper")

# ==========================================
# CONFIG (SMART CONTROL)
# ==========================================

MAX_RETRIES = 2
MAX_WORKERS = 1
SCROLL_STEPS = 5

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile",
    "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 Chrome/120 Mobile",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 390, "height": 844},
]

# ==========================================
# FINGERPRINT ENGINE (LIKE SCRAPELESS)
# ==========================================

def get_fingerprint():
    return {
        "user_agent": random.choice(USER_AGENTS),
        "viewport": random.choice(VIEWPORTS),
        "locale": random.choice(["en-US", "en-GB"]),
        "timezone_id": random.choice(["Asia/Karachi", "Europe/London"]),
    }

# ==========================================
# BLOCK DETECTION
# ==========================================

async def detect_block(page):
    html = await page.content()
    signals = ["captcha", "unusual traffic", "verify"]
    return any(s in html.lower() for s in signals)

# ==========================================
# HUMAN SIMULATION
# ==========================================

async def simulate_user(page):
    for _ in range(3):
        await page.mouse.move(random.randint(100, 600), random.randint(100, 500))
        await asyncio.sleep(random.uniform(0.3, 1))

# ==========================================
# AUTO PAGINATION ENGINE
# ==========================================

async def auto_scroll(page):
    for _ in range(SCROLL_STEPS):
        await page.mouse.wheel(0, 3000)
        await asyncio.sleep(1.5)

# ==========================================
# AI-STYLE PARSER (DOM BASED)
# ==========================================

async def parse_reviews(page) -> List[Dict[str, Any]]:
    elements = await page.query_selector_all("div[data-review-id]")

    results = []

    for el in elements:
        try:
            review_id = await el.get_attribute("data-review-id")

            author_el = await el.query_selector(".d4r55")
            rating_el = await el.query_selector("span[role='img']")
            text_el = await el.query_selector(".wiI7pd")

            author = await author_el.inner_text() if author_el else "Anonymous"

            rating_text = await rating_el.get_attribute("aria-label") if rating_el else "0"
            rating = int(rating_text[0]) if rating_text else 0

            text = await text_el.inner_text() if text_el else ""

            results.append({
                "review_id": review_id,
                "author_name": author,
                "rating": rating,
                "text": text,
            })

        except:
            continue

    return results

# ==========================================
# CORE SCRAPER ENGINE
# ==========================================

async def run_scraper(target: str, limit: int):

    fingerprint = get_fingerprint()

    async with async_playwright() as p:

        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            user_agent=fingerprint["user_agent"],
            viewport=fingerprint["viewport"],
            locale=fingerprint["locale"],
            timezone_id=fingerprint["timezone_id"],
        )

        page = await context.new_page()
        await stealth_async(page)

        try:
            await page.goto(target, timeout=30000)

            if await detect_block(page):
                raise Exception("Blocked")

            await simulate_user(page)
            await auto_scroll(page)

            data = await parse_reviews(page)

            await browser.close()

            return data[:limit]

        except Exception as e:
            await browser.close()
            logger.warning(f"⚠️ Playwright failed: {e}")
            return []

# ==========================================
# FALLBACK STRATEGY (SCRAPELESS STYLE)
# ==========================================

async def fallback(target: str):
    logger.warning("⚠️ Switching to fallback (API not configured)")
    return []

# ==========================================
# SMART ORCHESTRATOR
# ==========================================

async def orchestrator(target: str, limit: int):

    for attempt in range(MAX_RETRIES):

        logger.info(f"🔁 Attempt {attempt+1}")

        data = await run_scraper(target, limit)

        if data:
            return data

    # fallback if all failed
    return await fallback(target)

# ==========================================
# PUBLIC FUNCTION (ALIGNED WITH YOUR PROJECT)
# ==========================================

async def fetch_reviews(place_id: str, limit: int = 100):

    logger.info(f"🚀 Scrapeless-style scraping: {place_id}")

    if "http" in place_id:
        url = place_id
    else:
        url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

    data = await orchestrator(url, limit)

    logger.info(f"✅ Completed: {len(data)} reviews")

    return data


print("✅ SCRAPELESS-STYLE SCRAPER READY")
