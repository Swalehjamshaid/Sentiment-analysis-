import os
import asyncio
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# =========================
# LOGGING CONFIG
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper")


class ReviewScraper:
    def __init__(self):
        self.api_key = os.getenv("SERPAPI_KEY")
        if not self.api_key:
            raise ValueError("SERPAPI_KEY not set in environment")

        self.base_url = "https://serpapi.com/search.json"

        # Retry session
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1)
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    # =========================
    # STEP 1: RESOLVE DATA ID
    # =========================
    def resolve_to_data_id(self, query):
        params = {
            "engine": "google_maps",
            "q": query,
            "api_key": self.api_key
        }

        try:
            logger.info(f"Resolving data_id for: {query}")
            res = self.session.get(self.base_url, params=params, timeout=20)
            data = res.json()

            if "place_results" in data and data["place_results"].get("data_id"):
                return data["place_results"]["data_id"]

            local_results = data.get("local_results", [])
            if local_results:
                return local_results[0].get("data_id")

            return None

        except Exception as e:
            logger.error(f"ID resolution failed: {e}")
            return None

    # =========================
    # STEP 2: SERPAPI REVIEWS
    # =========================
    def get_reviews_serpapi(self, identifier, count=20):
        if not (str(identifier).startswith("0x") and ":" in str(identifier)):
            identifier = self.resolve_to_data_id(identifier)
            if not identifier:
                return []

        params = {
            "engine": "google_maps_reviews",
            "data_id": identifier,
            "api_key": self.api_key,
            "num": count,
            "sort_by": "newest"
        }

        try:
            logger.info("Fetching reviews via SerpApi...")
            res = self.session.get(self.base_url, params=params, timeout=30)
            res.raise_for_status()

            data = res.json()
            reviews = data.get("reviews", [])

            return [
                {
                    "user": r.get("user", {}).get("name"),
                    "rating": r.get("rating"),
                    "text": r.get("snippet") or r.get("text"),
                    "date": r.get("date"),
                    "source": "serpapi"
                }
                for r in reviews
            ]

        except Exception as e:
            logger.error(f"SerpApi failed: {e}")
            return []

    # =========================
    # STEP 3: PLAYWRIGHT FALLBACK
    # =========================
    async def get_reviews_playwright(self, query, max_reviews=20):
        logger.info("Fallback: Playwright scraping started...")

        reviews = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                await stealth_async(page)

                # Open Google Maps
                await page.goto(f"https://www.google.com/maps/search/{query}")
                await page.wait_for_timeout(5000)

                # Click first result
                try:
                    await page.click('a.hfpxzc', timeout=5000)
                except:
                    pass

                await page.wait_for_timeout(5000)

                # Click reviews button
                try:
                    await page.click('button[jsaction="pane.reviewChart.moreReviews"]', timeout=5000)
                except:
                    logger.warning("Could not click reviews button")

                await page.wait_for_timeout(5000)

                # Scroll to load reviews
                for _ in range(10):
                    await page.mouse.wheel(0, 3000)
                    await asyncio.sleep(2)

                elements = await page.query_selector_all('[data-review-id]')

                for el in elements[:max_reviews]:
                    try:
                        user = await el.query_selector('div.d4r55')
                        rating = await el.query_selector('span.kvMYJc')
                        text = await el.query_selector('span.wiI7pd')

                        reviews.append({
                            "user": await user.inner_text() if user else None,
                            "rating": await rating.get_attribute("aria-label") if rating else None,
                            "text": await text.inner_text() if text else None,
                            "source": "playwright"
                        })
                    except:
                        continue

                await browser.close()

        except Exception as e:
            logger.error(f"Playwright failed: {e}")

        return reviews

    # =========================
    # MAIN FUNCTION (HYBRID)
    # =========================
    async def get_reviews(self, identifier, count=20):
        # 1. Try SerpApi
        reviews = self.get_reviews_serpapi(identifier, count)

        if reviews:
            logger.info(f"✅ SerpApi success: {len(reviews)} reviews")
            return reviews

        # 2. Fallback to Playwright
        logger.warning("⚠️ SerpApi returned 0 → switching to Playwright")

        reviews = await self.get_reviews_playwright(identifier, count)

        if reviews:
            logger.info(f"✅ Playwright success: {len(reviews)} reviews")
        else:
            logger.error("❌ Both methods failed")

        return reviews


# =========================
# FASTAPI ENTRY
# =========================
async def fetch_reviews(data_id=None, **kwargs):
    identifier = data_id or kwargs.get("place_id") or kwargs.get("query")
    limit = kwargs.get("limit", 20)

    if not identifier:
        return []

    scraper = ReviewScraper()
    return await scraper.get_reviews(identifier, limit)
