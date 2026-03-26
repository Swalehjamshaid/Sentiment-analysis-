import asyncio
import json
import re
import random
import logging
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# =========================
# LOGGING CONFIG
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GoogleMaps.Scraper")

# =========================
# PROXY POOL
# =========================
PROXIES = [
    "http://user:pass@31.59.20.176:6754",
    "http://user:pass@23.95.150.145:6114",
    "http://user:pass@198.23.239.134:6540",
    "http://user:pass@45.38.107.97:6014",
    "http://user:pass@107.172.163.27:6543"
]

# =========================
# USER AGENTS
# =========================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
]

# =========================
# HELPER: PARSE PROXY
# =========================
def parse_proxy(proxy_url):
    if "@" in proxy_url:
        creds, server = proxy_url.split("@")
        username, password = creds.replace("http://", "").split(":")
        return {"server": f"http://{server}", "username": username, "password": password}
    return {"server": proxy_url}

# =========================
# MAIN SCRAPER FUNCTION
# =========================
async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Fetch Google Maps reviews using network interception with batchexecute.
    Returns a list of dictionaries with: review_id, author_name, rating, text, date_text.
    """
    logger.info(f"🚀 Initializing scraper for: {place_id}")
    reviews_data = []
    visited_ids = set()
    selected_proxy = parse_proxy(random.choice(PROXIES))

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy=selected_proxy,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process"
            ]
        )

        context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
        page = await context.new_page()
        await stealth_async(page)

        # ---------------------
        # NETWORK INTERCEPTION
        # ---------------------
        async def handle_response(response):
            if "batchexecute" not in response.url:
                return
            try:
                raw_text = await response.text()
                cleaned = raw_text.replace(")]}'", "").strip()
                matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned)

                for match in matches:
                    try:
                        inner_json = json.loads(json.loads(match)[2])
                        for block in inner_json:
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
                                                "scraped_at": datetime.utcnow().isoformat()
                                            })
                                            visited_ids.add(r_id)
                                    except (IndexError, TypeError):
                                        continue
                    except Exception:
                        continue
            except Exception:
                pass

        page.on("response", handle_response)

        # ---------------------
        # NAVIGATE TO PLACE
        # ---------------------
        url = place_id if place_id.startswith("http") else f"https://www.google.com/maps/place/?q=place_id:{place_id}&hl=en"

        try:
            await page.goto(url, wait_until="networkidle", timeout=90000)
            logger.info(f"🔗 Page loaded: {url}")

            # ---------------------
            # HUMAN-LIKE SCROLLING
            # ---------------------
            scrolls = 0
            max_scrolls = (limit // 10) + 15

            while len(reviews_data) < limit and scrolls < max_scrolls:
                await page.mouse.wheel(0, 4000)
                await asyncio.sleep(random.uniform(3.0, 5.0))
                scrolls += 1
                if reviews_data:
                    logger.info(f"📊 Progress: {len(reviews_data)} / {limit}")

        except Exception as e:
            logger.error(f"❌ Scraper failure: {str(e)}")

        finally:
            await browser.close()
            logger.info("✅ Browser closed successfully.")

    return reviews_data[:limit]

# =========================
# ALIAS FOR ROUTER / BACKEND
# =========================
scrape_google_reviews = fetch_reviews

# =========================
# OPTIONAL: CSV EXPORT
# =========================
def save_to_csv(data, filename="scraped_reviews.csv"):
    import csv
    if not data: return
    keys = data[0].keys()
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

# =========================
# TEST RUN
# =========================
if __name__ == "__main__":
    test_place_id = "ChIJZbR_3aO22YgROu6kdumheKA"
    reviews = asyncio.run(fetch_reviews(test_place_id, limit=20))
    print(f"Scraped {len(reviews)} reviews")
    for r in reviews:
        print(r)
