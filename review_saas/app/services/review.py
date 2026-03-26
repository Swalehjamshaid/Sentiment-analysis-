import asyncio
import json
import re
import random
import logging
import csv
import glob
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
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
# 🔥 CRITICAL FIX: Get Chromium path
# =========================
def get_chromium_path():
    paths = glob.glob("/ms-playwright/chromium-*/chrome-linux/chrome")
    if not paths:
        raise Exception("❌ Chromium not found in /ms-playwright")
    return paths[0]


# =========================
# MAIN SCRAPER
# =========================
async def fetch_reviews(place_id: str, limit: int = 50, retries: int = 3):
    for attempt in range(retries):
        try:
            return await _run_scraper(place_id, limit)
        except Exception as e:
            logger.warning(f"Retry {attempt+1} failed: {e}")
            await asyncio.sleep(3)

    logger.error("❌ All retries failed")
    return []


async def _run_scraper(place_id: str, limit: int):
    reviews_data = []
    visited_ids = set()

    proxy = parse_proxy(random.choice(PROXIES))

    async with async_playwright() as p:

        # 🔥 FORCE correct Chromium executable
        browser = await p.chromium.launch(
            headless=True,
            executable_path=get_chromium_path(),
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        context = await browser.new_context(
            proxy=proxy,
            user_agent=random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            ])
        )

        page = await context.new_page()
        await stealth_async(page)

        # =========================
        # INTERCEPTOR
        # =========================
        async def handle_response(response):
            try:
                if "batchexecute" not in response.url:
                    return

                text = await response.text()
                cleaned = text.replace(")]}'", "").strip()

                matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned)

                for match in matches:
                    try:
                        inner = json.loads(json.loads(match)[2])

                        for block in inner:
                            if isinstance(block, list):
                                for r in block:
                                    try:
                                        r_id = r[0]
                                        if r_id not in visited_ids:
                                            reviews_data.append({
                                                "review_id": r_id,
                                                "author_name": r[1][0],
                                                "rating": r[4],
                                                "text": r[3],
                                                "date_text": r[27] if len(r) > 27 else "N/A",
                                                "scraped_at": datetime.now().isoformat()
                                            })
                                            visited_ids.add(r_id)
                                    except Exception:
                                        continue
                    except Exception:
                        continue

            except Exception as e:
                logger.debug(f"Interceptor error: {e}")

        page.on("response", handle_response)

        # =========================
        # NAVIGATION
        # =========================
        if str(place_id).startswith("http"):
            url = f"{place_id}&hl=en"
        else:
            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}&hl=en"

        await page.goto(url, wait_until="networkidle", timeout=90000)

        # =========================
        # SCROLL
        # =========================
        scrolls = 0
        max_scrolls = (limit // 10) + 20

        while len(reviews_data) < limit and scrolls < max_scrolls:
            await page.mouse.wheel(0, random.randint(3000, 6000))
            await asyncio.sleep(random.uniform(2.5, 4.5))
            scrolls += 1

            logger.info(f"Progress: {len(reviews_data)} / {limit}")

        await browser.close()
        logger.info("✅ Browser closed")

    return reviews_data[:limit]


# =========================
# EXPORT
# =========================
scrape_google_reviews = fetch_reviews


def save_to_csv(data, filename="scraped_reviews.csv"):
    if not data:
        return
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
