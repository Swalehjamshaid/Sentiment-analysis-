import asyncio
import random
from typing import List, Dict, Any, Optional

import httpx
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# ==========================================
# CONFIG
# ==========================================

MAX_RETRIES = 3
MAX_WORKERS = 3
SCROLL_ROUNDS = 6

# 🔥 Add REAL geo proxies here
PROXIES = [
    None,
    # "http://user:pass@us-proxy:port",
    # "http://user:pass@eu-proxy:port",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X) Chrome/119 Safari/537.36",
]

# Optional API fallback (Outscraper / Scrapeless)
SCRAPER_API_KEY = None  # put key here

# ==========================================
# PROXY MANAGER
# ==========================================

class ProxyManager:
    def __init__(self, proxies):
        self.proxies = proxies.copy()
        self.fail_count = {p: 0 for p in proxies}

    def get_proxy(self):
        if not self.proxies:
            return None
        return random.choice(self.proxies)

    def mark_failure(self, proxy):
        if proxy not in self.fail_count:
            return
        self.fail_count[proxy] += 1
        if self.fail_count[proxy] >= 3 and proxy in self.proxies:
            print(f"❌ Removing bad proxy: {proxy}")
            self.proxies.remove(proxy)

    def mark_success(self, proxy):
        if proxy in self.fail_count:
            self.fail_count[proxy] = max(0, self.fail_count[proxy] - 1)

proxy_manager = ProxyManager(PROXIES)

# ==========================================
# HUMAN BEHAVIOR
# ==========================================

async def simulate_human(page):
    for _ in range(3):
        await page.mouse.move(random.randint(100, 800), random.randint(100, 600))
        await asyncio.sleep(random.uniform(0.5, 1.5))

async def scroll_reviews(page):
    for _ in range(SCROLL_ROUNDS):
        await page.mouse.wheel(0, random.randint(1500, 3000))
        await asyncio.sleep(random.uniform(1, 2))

# ==========================================
# 🔥 AI-STYLE DOM PARSER (NO BATCHEXECUTE)
# ==========================================

async def extract_reviews_dom(page) -> List[Dict[str, Any]]:
    reviews = []

    try:
        elements = await page.query_selector_all("div[role='article']")

        for el in elements:
            try:
                author = await el.query_selector("div.d4r55")
                rating = await el.query_selector("span.kvMYJc")
                text = await el.query_selector("span.wiI7pd")

                reviews.append({
                    "review_id": str(hash(await el.inner_text())),
                    "author_name": await author.inner_text() if author else "Anonymous",
                    "rating": int((await rating.get_attribute("aria-label")).split()[0]) if rating else 0,
                    "text": await text.inner_text() if text else "",
                })
            except:
                continue

    except Exception as e:
        print("DOM parse error:", e)

    return reviews

# ==========================================
# PLAYWRIGHT SCRAPER
# ==========================================

async def scrape_with_browser(target: str) -> List[Dict]:

    proxy = proxy_manager.get_proxy()

    try:
        async with async_playwright() as p:

            browser = await p.chromium.launch(
                headless=True,
                proxy={"server": proxy} if proxy else None,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )

            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                locale="en-US"
            )

            page = await context.new_page()
            await stealth_async(page)

            # Build URL
            if "http" in target:
                url = target
            else:
                url = f"https://www.google.com/maps/place/?q=place_id:{target}"

            await page.goto(url, timeout=60000)
            await page.wait_for_load_state("domcontentloaded")

            # Accept cookies
            try:
                await page.click("button:has-text('I agree')", timeout=3000)
            except:
                pass

            await simulate_human(page)

            # Click reviews tab
            try:
                await page.click("button[jsaction*='pane.reviewChart.moreReviews']", timeout=5000)
            except:
                pass

            await scroll_reviews(page)

            reviews = await extract_reviews_dom(page)

            await browser.close()

            if reviews:
                proxy_manager.mark_success(proxy)
            else:
                proxy_manager.mark_failure(proxy)

            return reviews

    except Exception as e:
        print("❌ Browser scrape failed:", e)
        proxy_manager.mark_failure(proxy)
        return []

# ==========================================
# 🔥 API FALLBACK
# ==========================================

async def scrape_with_api(target: str) -> List[Dict]:

    if not SCRAPER_API_KEY:
        return []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://api.app.outscraper.com/maps/reviews",
                params={
                    "query": target,
                    "limit": 100,
                    "async": False
                },
                headers={"X-API-KEY": SCRAPER_API_KEY}
            )

            data = response.json()

            results = []
            for item in data.get("data", []):
                for r in item.get("reviews_data", []):
                    results.append({
                        "review_id": r.get("review_id"),
                        "author_name": r.get("author_title"),
                        "rating": r.get("review_rating"),
                        "text": r.get("review_text"),
                    })

            return results

    except Exception as e:
        print("❌ API fallback failed:", e)
        return []

# ==========================================
# WORKER SYSTEM
# ==========================================

async def worker(queue: asyncio.Queue, results: List):

    while not queue.empty():
        target = await queue.get()

        try:
            # 1️⃣ Try browser
            data = await scrape_with_browser(target)

            # 2️⃣ Fallback if blocked
            if not data:
                print("⚠️ Switching to API fallback...")
                data = await scrape_with_api(target)

            if data:
                results.extend(data)

        except Exception as e:
            print("Worker error:", e)

        finally:
            queue.task_done()

# ==========================================
# ENGINE
# ==========================================

async def scrape_engine(target: str, limit: int):

    queue = asyncio.Queue()

    for _ in range(MAX_RETRIES):
        await queue.put(target)

    results = []

    workers = [
        asyncio.create_task(worker(queue, results))
        for _ in range(MAX_WORKERS)
    ]

    await queue.join()

    for w in workers:
        w.cancel()

    # Deduplicate
    unique = {}
    for r in results:
        unique[r["review_id"]] = r

    return list(unique.values())[:limit]

# ==========================================
# PUBLIC FUNCTION (MATCHES YOUR PROJECT)
# ==========================================

async def fetch_reviews(place_id: str, limit: int = 300) -> List[Dict]:
    return await scrape_engine(place_id, limit)

print("✅ HYBRID SCRAPER READY (Playwright + API + AI parsing)")
