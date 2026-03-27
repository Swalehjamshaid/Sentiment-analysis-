import os
import asyncio
import logging
import requests
from itertools import cycle
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
        # ✅ API KEY (supports both names)
        self.api_key = os.getenv("SERP_API_KEY") or os.getenv("SERPAPI_KEY")

        if self.api_key:
            logger.info("✅ SERP API key loaded")
        else:
            logger.warning("⚠️ No SERP API key → using proxies + Playwright")

        self.base_url = "https://serpapi.com/search.json"

        # =========================
        # 🔥 YOUR WEBSHARE PROXIES
        # =========================
        self.proxy_list = [
            "http://dkgjitgr:uzeqkqwjvmqe@31.59.20.176:6754",
            "http://dkgjitgr:uzeqkqwjvmqe@23.95.150.145:6114",
            "http://dkgjitgr:uzeqkqwjvmqe@198.23.239.134:6540",
            "http://dkgjitgr:uzeqkqwjvmqe@45.38.107.97:6014",
            "http://dkgjitgr:uzeqkqwjvmqe@107.172.163.27:6543",
            "http://dkgjitgr:uzeqkqwjvmqe@198.105.121.200:6462",
            "http://dkgjitgr:uzeqkqwjvmqe@216.10.27.159:6837",
            "http://dkgjitgr:uzeqkqwjvmqe@142.111.xxx.xxx:5611",  # replace properly
            "http://dkgjitgr:uzeqkqwjvmqe@191.96.254.138:6185"
        ]

        self.proxy_pool = cycle(self.proxy_list)

        # Retry session
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1)
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    # =========================
    # GET NEXT PROXY
    # =========================
    def get_proxy(self):
        proxy = next(self.proxy_pool)
        return {
            "http": proxy,
            "https": proxy
        }

    # =========================
    # RESOLVE DATA ID
    # =========================
    def resolve_to_data_id(self, query):
        if not self.api_key:
            return None

        params = {
            "engine": "google_maps",
            "q": query,
            "api_key": self.api_key
        }

        try:
            proxy = self.get_proxy()
            logger.info(f"Resolving ID using proxy: {proxy['http']}")

            res = self.session.get(
                self.base_url,
                params=params,
                proxies=proxy,
                timeout=20
            )

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
    # SERPAPI REVIEWS
    # =========================
    def get_reviews_serpapi(self, identifier, count=20):
        if not self.api_key:
            return []

        if not (str(identifier).startswith("0x") and ":" in str(identifier)):
            identifier = self.resolve_to_data_id(identifier)
            if not identifier:
                return []

        params = {
            "engine": "google_maps_reviews",
            "data_id": identifier,
            "api_key": self.api_key,
            "num": count
        }

        try:
            proxy = self.get_proxy()

            logger.info(f"Fetching SerpApi with proxy: {proxy['http']}")

            res = self.session.get(
                self.base_url,
                params=params,
                proxies=proxy,
                timeout=30
            )

            res.raise_for_status()
            data = res.json()

            return data.get("reviews", [])

        except Exception as e:
            logger.error(f"SerpApi failed: {e}")
            return []

    # =========================
    # PLAYWRIGHT WITH PROXY
    # =========================
    async def get_reviews_playwright(self, query, max_reviews=20):
        logger.info("🚀 Playwright scraping with proxy...")

        reviews = []
        proxy_url = next(self.proxy_pool)

        try:
            proxy_parts = proxy_url.replace("http://", "").split("@")
            creds, host = proxy_parts
            username, password = creds.split(":")
            server = f"http://{host}"

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    proxy={
                        "server": server,
                        "username": username,
                        "password": password
                    }
                )

                context = await browser.new_context()
                page = await context.new_page()

                await stealth_async(page)

                await page.goto(f"https://www.google.com/maps/search/{query}")
                await page.wait_for_timeout(5000)

                try:
                    await page.click('a.hfpxzc', timeout=5000)
                except:
                    pass

                await page.wait_for_timeout(5000)

                try:
                    await page.click('button[jsaction="pane.reviewChart.moreReviews"]')
                except:
                    pass

                for _ in range(10):
                    await page.mouse.wheel(0, 3000)
                    await asyncio.sleep(2)

                elements = await page.query_selector_all('[data-review-id]')

                for el in elements[:max_reviews]:
                    try:
                        user = await el.query_selector('div.d4r55')
                        text = await el.query_selector('span.wiI7pd')

                        reviews.append({
                            "user": await user.inner_text() if user else None,
                            "text": await text.inner_text() if text else None,
                            "source": "playwright_proxy"
                        })
                    except:
                        continue

                await browser.close()

        except Exception as e:
            logger.error(f"Playwright proxy failed: {e}")

        return reviews

    # =========================
    # MAIN FUNCTION
    # =========================
    async def get_reviews(self, identifier, count=20):

        # 1. Try SerpApi
        reviews = self.get_reviews_serpapi(identifier, count)

        if reviews:
            logger.info(f"✅ SerpApi success: {len(reviews)}")
            return reviews

        # 2. Fallback Playwright
        logger.warning("⚠️ Switching to Playwright with proxy...")

        return await self.get_reviews_playwright(identifier, count)


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
