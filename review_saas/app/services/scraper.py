import asyncio
import json
import re
import random
import logging
import glob
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReviewSaaS.Scraper")

# =========================
# PROXIES
# =========================
PROXIES = [
    "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
    "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
    "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
    "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
    "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
]

# =========================
# FIX: GET CHROMIUM PATH
# =========================
def get_chromium_path():
    paths = glob.glob("/ms-playwright/chromium-*/chrome-linux/chrome")
    if not paths:
        raise Exception("❌ Chromium not found. Fix Dockerfile.")
    return paths[0]

# =========================
# PROXY PARSER
# =========================
def parse_proxy(proxy_url):
    if "@" in proxy_url:
        creds, server = proxy_url.split("@")
        username, password = creds.replace("http://", "").split(":")
        return {
            "server": f"http://{server}",
            "username": username,
            "password": password
        }
    return {"server": proxy_url}

# =========================
# MAIN SCRAPER
# =========================
async def fetch_reviews(place_id: str, limit: int = 50, retries: int = 3):
    logger.info(f"🚀 Starting scraper for: {place_id}")

    for attempt in range(retries):
        try:
            return await _scrape(place_id, limit)
        except Exception as e:
            logger.warning(f"Retry {attempt+1} failed: {e}")
            await asyncio.sleep(3)

    logger.error("❌ All retries failed")
    return []

# =========================
# CORE LOGIC
# =========================
async def _scrape(place_id: str, limit: int):
    reviews = []
    seen_ids = set()

    proxy = parse_proxy(random.choice(PROXIES))

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=get_chromium_path(),  # 🔥 FIXED
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        context = await browser.new_context(proxy=proxy)
        page = await context.new_page()
        await stealth_async(page)

        # =========================
        # INTERCEPT REVIEWS
        # =========================
        async def handle_response(response):
            if "batchexecute" not in response.url:
                return

            try:
                text = await response.text()
                cleaned = text.replace(")]}'", "").strip()

                matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned)

                for match in matches:
                    try:
                        data = json.loads(json.loads(match)[2])

                        for block in data:
                            if isinstance(block, list):
                                for r in block:
                                    try:
                                        rid = r[0]
                                        if rid not in seen_ids:
                                            reviews.append({
                                                "review_id": rid,
                                                "author_name": r[1][0],
                                                "rating": r[4],
                                                "text": r[3],
                                                "date_text": r[27] if len(r) > 27 else "",
                                                "scraped_at": datetime.utcnow().isoformat()
                                            })
                                            seen_ids.add(rid)
                                    except:
                                        continue
                    except:
                        continue
            except:
                pass

        page.on("response", handle_response)

        # =========================
        # OPEN GOOGLE MAPS
        # =========================
        url = (
            place_id if place_id.startswith("http")
            else f"https://www.google.com/maps/place/?q=place_id:{place_id}&hl=en"
        )

        await page.goto(url, timeout=120000)

        # =========================
        # CLICK REVIEWS BUTTON
        # =========================
        try:
            await page.click('button[jsaction*="pane.reviewChart.moreReviews"]', timeout=10000)
            logger.info("✅ Opened reviews panel")
        except:
            logger.warning("⚠ Could not click reviews button")

        await asyncio.sleep(3)

        # =========================
        # SCROLL REVIEWS PANEL
        # =========================
        scroll_box = await page.query_selector('div[role="feed"]')

        if not scroll_box:
            raise Exception("❌ Reviews container not found")

        scrolls = 0
        max_scrolls = (limit // 10) + 20

        while len(reviews) < limit and scrolls < max_scrolls:
            await scroll_box.evaluate("el => el.scrollBy(0, 3000)")
            await asyncio.sleep(random.uniform(2, 4))
            scrolls += 1
            logger.info(f"Progress: {len(reviews)} / {limit}")

        await browser.close()
        logger.info("✅ Browser closed")

    return reviews[:limit]

# =========================
# EXPORT
# =========================
scrape_google_reviews = fetch_reviews
