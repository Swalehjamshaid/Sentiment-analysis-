import asyncio
import json
import random
import re
from typing import List, Dict, Any

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# ==========================================
# CONFIG
# ==========================================

MAX_RETRIES = 4
MAX_WORKERS = 3
SCROLL_STEPS = 6

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/119 Safari/537.36",
]

PROXIES = [
    None,
    # "http://user:pass@ip:port",
]

SESSION_FILE = "session.json"

# ==========================================
# 🔥 PROXY MANAGER
# ==========================================

class ProxyManager:
    def __init__(self, proxies):
        self.proxies = proxies.copy()
        self.fail_count = {p: 0 for p in proxies}

    def get_proxy(self):
        if not self.proxies:
            return None
        sorted_proxies = sorted(self.proxies, key=lambda p: self.fail_count.get(p, 0))
        return random.choice(sorted_proxies[:2])

    def mark_success(self, proxy):
        if proxy in self.fail_count:
            self.fail_count[proxy] = max(0, self.fail_count[proxy] - 1)

    def mark_failure(self, proxy):
        if proxy not in self.fail_count:
            return
        self.fail_count[proxy] += 1

        if self.fail_count[proxy] >= 3:
            print(f"❌ Removing bad proxy: {proxy}")
            self.proxies.remove(proxy)


proxy_manager = ProxyManager(PROXIES)

# ==========================================
# HUMAN SIMULATION
# ==========================================

async def simulate_human(page):
    for _ in range(4):
        await page.mouse.move(random.randint(100, 900), random.randint(100, 700))
        await asyncio.sleep(random.uniform(0.3, 1.0))

    for _ in range(SCROLL_STEPS):
        await page.mouse.wheel(0, random.randint(1500, 3500))
        await asyncio.sleep(random.uniform(1, 2.5))


# ==========================================
# PARSER (batchexecute)
# ==========================================

def parse_batchexecute(text: str) -> List[Dict[str, Any]]:
    try:
        cleaned = text.replace(")]}'", "")
        matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned)

        reviews = []

        for match in matches:
            try:
                data = json.loads(match)
                payload = data[2]

                if isinstance(payload, str):
                    inner = json.loads(payload)

                    for block in inner:
                        for r in block:
                            try:
                                reviews.append({
                                    "author": r[0][1],
                                    "rating": r[4],
                                    "text": r[3],
                                })
                            except:
                                continue
            except:
                continue

        return reviews

    except Exception as e:
        print("Parse Error:", e)
        return []


# ==========================================
# SINGLE SCRAPE TASK
# ==========================================

async def run_single_scrape(url: str) -> List[Dict]:

    playwright = await async_playwright().start()

    proxy = proxy_manager.get_proxy()

    browser = await playwright.chromium.launch(
        headless=True,
        proxy={"server": proxy} if proxy else None
    )

    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS)
    )

    page = await context.new_page()
    await stealth_async(page)

    batchexecute_data = []

    async def handle_response(response):
        try:
            if "batchexecute" in response.url:
                batchexecute_data.append(await response.text())
        except:
            pass

    page.on("response", handle_response)

    try:
        await page.goto(url, timeout=60000)
        await page.wait_for_load_state("domcontentloaded")

        # Consent
        try:
            await page.click("button:has-text('I agree')", timeout=5000)
        except:
            pass

        await simulate_human(page)
        await asyncio.sleep(3)

        await browser.close()
        await playwright.stop()

        all_reviews = []
        for raw in batchexecute_data:
            all_reviews.extend(parse_batchexecute(raw))

        if all_reviews:
            proxy_manager.mark_success(proxy)
        else:
            proxy_manager.mark_failure(proxy)

        return all_reviews

    except Exception as e:
        print(f"❌ Proxy {proxy} failed:", e)
        proxy_manager.mark_failure(proxy)

        await browser.close()
        await playwright.stop()

        return []


# ==========================================
# WORKER SYSTEM
# ==========================================

async def worker(queue: asyncio.Queue, results: List):

    while not queue.empty():
        url = await queue.get()

        try:
            data = await run_single_scrape(url)
            if data:
                results.extend(data)
        except Exception as e:
            print("Worker error:", e)

        finally:
            queue.task_done()


# ==========================================
# MAIN ENGINE
# ==========================================

async def scrape_google_reviews(url: str):

    queue = asyncio.Queue()

    # Add retry tasks
    for _ in range(MAX_RETRIES):
        await queue.put(url)

    results = []

    workers = [
        asyncio.create_task(worker(queue, results))
        for _ in range(MAX_WORKERS)
    ]

    await queue.join()

    for w in workers:
        w.cancel()

    # Deduplicate
    unique_reviews = {
        f"{r['author']}_{r['text'][:50]}": r
        for r in results
    }.values()

    return {
        "success": len(unique_reviews) > 0,
        "count": len(unique_reviews),
        "reviews": list(unique_reviews)[:50]
    }


# ==========================================
# 🔥 PUBLIC FUNCTION (FIXED)
# ==========================================

async def fetch_reviews(url: str):
    return await scrape_google_reviews(url)


# DEBUG (to confirm Railway loads correct file)
print("✅ scraper.py fully loaded with workers + proxy system")
