import asyncio
import random
import logging
import requests
import os
from datetime import datetime
from playwright.async_api import async_playwright

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("scraper")


class SaaSReviewScraper:
    def __init__(self):
        self.api_key = os.getenv("SERP_API_KEY")
        self.scrapeless_key = os.getenv("SCRAPELESS_API_KEY")

        if not self.api_key:
            raise ValueError("❌ SERP_API_KEY not set")

        # =========================
        # PROXY POOL
        # =========================
        self.proxies = [
            {
                "server": "http://31.59.20.176:6754",
                "username": "dkgjitgr",
                "password": "uzeqkqwjvmqe"
            }
        ]

    # =========================
    # PROXY ROTATION
    # =========================
    def get_proxy(self):
        if not self.proxies:
            return None
        return random.choice(self.proxies)

    # =========================
    # SERPAPI → PLACE ID
    # =========================
    def get_place_id(self, query):
        try:
            logger.info(f"🔍 Resolving place_id for: {query}")

            url = "https://serpapi.com/search.json"
            params = {
                "engine": "google_maps",
                "q": query,
                "api_key": self.api_key
            }

            res = requests.get(url, params=params, timeout=20)

            if res.status_code != 200:
                logger.error(f"SerpAPI error: {res.text}")
                return None

            data = res.json()
            place_id = data.get("place_results", {}).get("place_id")

            if not place_id:
                logger.warning("⚠️ No place_id found")
                return None

            logger.info(f"✅ place_id: {place_id}")
            return place_id

        except Exception as e:
            logger.error(f"❌ SerpAPI failed: {e}")
            return None

    # =========================
    # PLAYWRIGHT SCRAPER
    # =========================
    async def scrape_playwright(self, place_id, use_proxy=True):
        reviews = []
        url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

        try:
            proxy = self.get_proxy() if use_proxy else None

            logger.info(f"🚀 Playwright start (proxy={use_proxy})")

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    proxy=proxy
                )

                page = await browser.new_page()

                await page.goto(url, timeout=60000)
                await page.wait_for_timeout(5000)

                # Scroll to load reviews
                for _ in range(7):
                    await page.mouse.wheel(0, 5000)
                    await page.wait_for_timeout(2000)

                cards = await page.query_selector_all(".jftiEf")

                for c in cards:
                    try:
                        author = await c.query_selector_eval(
                            ".d4r55", "el => el.innerText"
                        )
                        rating = await c.query_selector_eval(
                            ".kvMYJc", "el => el.getAttribute('aria-label')"
                        )
                        text = await c.query_selector_eval(
                            ".wiI7pd", "el => el.innerText"
                        )

                        reviews.append({
                            "author": author,
                            "rating": rating,
                            "text": text,
                            "source": "google_maps",
                            "scraped_at": datetime.utcnow().isoformat()
                        })

                    except:
                        continue

                await browser.close()

                logger.info(f"✅ Playwright reviews: {len(reviews)}")
                return reviews

        except Exception as e:
            logger.error(f"❌ Playwright failed: {e}")
            return []

    # =========================
    # SCRAPELESS BACKUP
    # =========================
    def scrape_scrapeless(self, query):
        if not self.scrapeless_key:
            return []

        try:
            logger.info("⚡ Scrapeless fallback")

            url = "https://api.scrapeless.com/v1/scrape"

            headers = {
                "Authorization": f"Bearer {self.scrapeless_key}"
            }

            payload = {
                "query": query,
                "source": "google_maps_reviews"
            }

            res = requests.post(url, json=payload, headers=headers, timeout=20)

            if res.status_code == 200:
                return res.json().get("reviews", [])

            return []

        except Exception as e:
            logger.error(f"❌ Scrapeless failed: {e}")
            return []

    # =========================
    # MAIN PIPELINE
    # =========================
    async def get_reviews(self, query):
        logger.info(f"🚀 START: {query}")

        # Step 1: place_id
        place_id = self.get_place_id(query)

        if not place_id:
            logger.warning("⚠️ No place_id → Scrapeless")
            return self.scrape_scrapeless(query)

        # Step 2: Playwright with proxy
        reviews = await self.scrape_playwright(place_id, True)

        # Step 3: Retry without proxy
        if not reviews:
            logger.warning("⚠️ Retry without proxy")
            reviews = await self.scrape_playwright(place_id, False)

        # Step 4: Scrapeless fallback
        if not reviews:
            logger.warning("⚠️ Scrapeless fallback")
            reviews = self.scrape_scrapeless(query)

        logger.info(f"🎯 FINAL COUNT: {len(reviews)}")
        return reviews


# =========================
# ✅ FIX FOR YOUR ERROR
# =========================
async def fetch_reviews(query: str):
    scraper = SaaSReviewScraper()
    return await scraper.get_reviews(query)


# =========================
# OPTIONAL BULK FUNCTION
# =========================
async def bulk_scrape(queries):
    scraper = SaaSReviewScraper()
    tasks = [scraper.get_reviews(q) for q in queries]
    results = await asyncio.gather(*tasks)
    return dict(zip(queries, results))
