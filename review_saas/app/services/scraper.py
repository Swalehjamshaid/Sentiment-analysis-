import asyncio
import requests
import logging
import os
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper")


class ReviewScraper:
    def __init__(self):
        self.api_key = os.getenv("SERP_API_KEY")

        # Proxy (ONLY for Playwright)
        self.proxy = {
            "server": "http://31.59.20.176:6754",
            "username": "dkgjitgr",
            "password": "uzeqkqwjvmqe"
        }

    # =========================
    # STEP 1: GET PLACE ID
    # =========================
    def get_place_id(self, query):
        try:
            logger.info("🔍 Resolving place_id via SerpAPI (NO proxy)")

            url = "https://serpapi.com/search.json"
            params = {
                "engine": "google_maps",
                "q": query,
                "api_key": self.api_key
            }

            res = requests.get(url, params=params, timeout=30)
            data = res.json()

            if "place_results" in data:
                place_id = data["place_results"].get("place_id")
                logger.info(f"✅ place_id found: {place_id}")
                return place_id

            logger.error("❌ No place_id found")
            return None

        except Exception as e:
            logger.error(f"❌ SerpAPI failed: {e}")
            return None

    # =========================
    # STEP 2: PLAYWRIGHT SCRAPER
    # =========================
    async def scrape_reviews_playwright(self, place_id, use_proxy=True):
        reviews = []

        url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

        try:
            logger.info(f"🚀 Playwright scraping (proxy={use_proxy})")

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    proxy=self.proxy if use_proxy else None
                )

                page = await browser.new_page()

                await page.goto(url, timeout=60000)

                await page.wait_for_timeout(5000)

                # Scroll to load reviews
                for _ in range(5):
                    await page.mouse.wheel(0, 3000)
                    await page.wait_for_timeout(2000)

                elements = await page.query_selector_all(".jftiEf")

                for el in elements:
                    try:
                        name = await el.query_selector_eval(
                            ".d4r55", "el => el.innerText"
                        )
                        rating = await el.query_selector_eval(
                            ".kvMYJc", "el => el.getAttribute('aria-label')"
                        )
                        text = await el.query_selector_eval(
                            ".wiI7pd", "el => el.innerText"
                        )

                        reviews.append({
                            "author": name,
                            "rating": rating,
                            "text": text
                        })

                    except:
                        continue

                await browser.close()

                logger.info(f"✅ Reviews scraped: {len(reviews)}")
                return reviews

        except Exception as e:
            logger.error(f"❌ Playwright failed: {e}")
            return []

    # =========================
    # MAIN FUNCTION
    # =========================
    async def get_reviews(self, query):
        place_id = self.get_place_id(query)

        if not place_id:
            return []

        # Try with proxy
        reviews = await self.scrape_reviews_playwright(place_id, use_proxy=True)

        # Fallback: retry without proxy
        if len(reviews) == 0:
            logger.warning("⚠️ Retrying WITHOUT proxy...")
            reviews = await self.scrape_reviews_playwright(place_id, use_proxy=False)

        return reviews


# =========================
# RUN TEST
# =========================
if __name__ == "__main__":
    scraper = ReviewScraper()

    result = asyncio.run(
        scraper.get_reviews("Salt'n Pepper Village Lahore")
    )

    print(f"\n🔥 TOTAL REVIEWS: {len(result)}\n")
    print(result[:3])
