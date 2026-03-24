import asyncio
import json
import re
import random
import logging

# Engines
from patchright.async_api import async_playwright as patchright_playwright
from playwright.async_api import async_playwright as playwright
from playwright_stealth import stealth_async

# Optional fallback
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("multi.scraper")


# ================================
# COMMON PROXY POOL
# ================================
PROXIES = [
    "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
    "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
    "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
    "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
    "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
]


# ================================
# ENGINE 1: PATCHRIGHT (BEST)
# ================================
async def engine_patchright(place_id, limit):
    logger.info("🚀 Engine 1: Patchright Starting")

    proxy = random.choice(PROXIES)

    async with patchright_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": proxy}
        )

        context = await browser.new_context()
        page = await context.new_page()
        await stealth_async(page)

        reviews = []

        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    clean = text.replace(")]}'", "")
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', clean)

                    for m in matches:
                        raw = json.loads(m)
                        inner = json.loads(raw[2])

                        for block in inner:
                            for r in block:
                                try:
                                    reviews.append({
                                        "review_id": r[0],
                                        "author": r[1][0],
                                        "rating": r[4],
                                        "text": r[3]
                                    })
                                except:
                                    continue
                except:
                    pass

        page.on("response", handle_response)

        url = f"https://www.google.com/maps/search/?api=1&query_place_id={place_id}&hl=en"

        await page.goto(url, wait_until="networkidle", timeout=60000)

        try:
            await page.wait_for_selector('.wiI7eb', timeout=10000)
        except:
            pass

        for _ in range(10):
            await page.mouse.wheel(0, 3000)
            await asyncio.sleep(random.uniform(3, 6))

        await browser.close()

        logger.info(f"Patchright got {len(reviews)} reviews")
        return reviews[:limit]


# ================================
# ENGINE 2: PLAYWRIGHT (NO STEALTH)
# ================================
async def engine_playwright(place_id, limit):
    logger.info("⚙️ Engine 2: Playwright Starting")

    async with playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        reviews = []

        try:
            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            await page.goto(url, timeout=60000)

            await page.wait_for_timeout(5000)

            elements = await page.query_selector_all('.wiI7eb')

            for el in elements:
                text = await el.inner_text()
                reviews.append({"text": text})

        except Exception as e:
            logger.warning(f"Playwright failed: {e}")

        await browser.close()
        return reviews[:limit]


# ================================
# ENGINE 3: REQUESTS (FAST API HACK)
# ================================
def engine_requests(place_id, limit):
    logger.info("🌐 Engine 3: Requests Starting")

    try:
        url = "https://www.google.com/maps/preview/review/listentitiesreviews"

        params = {
            "authuser": "0",
            "hl": "en",
            "gl": "us",
            "pb": f"!1m2!1y{place_id}!2y0"
        }

        res = requests.get(url, params=params, timeout=10)

        if res.status_code == 200:
            data = res.text
            matches = re.findall(r'\[\[".*?"\]\]', data)

            return [{"raw": m} for m in matches[:limit]]

    except Exception as e:
        logger.warning(f"Requests failed: {e}")

    return []


# ================================
# ENGINE 4: FINAL FALLBACK
# ================================
async def engine_empty(place_id, limit):
    logger.warning("⚠️ All engines failed")
    return []


# ================================
# MASTER CONTROLLER
# ================================
async def fetch_reviews(place_id: str, limit: int = 50):

    engines = [
        engine_patchright,
        engine_playwright,
        lambda p, l: asyncio.to_thread(engine_requests, p, l)
    ]

    for engine in engines:
        try:
            logger.info(f"🔄 Trying engine: {engine.__name__}")

            if asyncio.iscoroutinefunction(engine):
                result = await engine(place_id, limit)
            else:
                result = await engine(place_id, limit)

            if result and len(result) > 5:
                logger.info(f"✅ SUCCESS with {engine.__name__}")
                return result

        except Exception as e:
            logger.error(f"❌ Engine failed: {engine.__name__} | {e}")

    return await engine_empty(place_id, limit)
