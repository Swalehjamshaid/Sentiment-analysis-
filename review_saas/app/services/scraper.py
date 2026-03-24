import asyncio
import json
import random
import re
import uuid
from typing import List, Dict, Any

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# ==========================================
# CONFIG
# ==========================================

MAX_RETRIES = 4
MAX_WORKERS = 3
SCROLL_PAUSE = (1.5, 3.0)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/119 Safari/537.36",
]

PROXIES = [
    None,
    # "http://user:pass@ip:port",
]

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
# 🔥 UTIL
# ==========================================

def build_url(place_id: str):
    if "http" in place_id:
        return place_id
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"

def is_blocked(content: str) -> bool:
    block_signals = [
        "unusual traffic",
        "not a robot",
        "captcha",
        "blocked",
    ]
    return any(signal in content.lower() for signal in block_signals)

# ==========================================
# 🔥 HUMAN SIMULATION
# ==========================================

async def simulate_human(page):
    for _ in range(5):
        await page.mouse.move(random.randint(100, 900), random.randint(100, 700))
        await asyncio.sleep(random.uniform(0.3, 1.2))

# ==========================================
# 🔥 AUTO PAGINATION (SCROLL ENGINE)
# ==========================================

async def auto_scroll(page, limit=200):
    last_height = 0
    collected = 0

    while collected < limit:
        await page.mouse.wheel(0, random.randint(2000, 4000))
        await asyncio.sleep(random.uniform(*SCROLL_PAUSE))

        new_height = await page.evaluate("document.body.scrollHeight")

        if new_height == last_height:
            break

        last_height = new_height
        collected += 20  # approx reviews per scroll

# ==========================================
# 🔥 PARSER
# ==========================================

def parse_batchexecute(text: str) -> List[Dict[str, Any]]:
    results = []

    try:
        cleaned = text.replace(")]}'", "")
        matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned)

        for match in matches:
            try:
                data = json.loads(match)
                payload = data[2]

                if isinstance(payload, str):
                    inner = json.loads(payload)

                    for block in inner:
                        for r in block:
                            try:
                                results.append({
                                    "review_id": str(uuid.uuid4()),  # 🔥 unique ID
                                    "author_name": r[0][1],
                                    "rating": r[4],
                                    "text": r[3],
                                })
                            except:
                                continue
            except:
                continue

    except Exception as e:
        print("Parse Error:", e)

    return results

# ==========================================
# 🔥 SINGLE SCRAPE TASK
# ==========================================

async def run_scrape(place_id: str, limit: int):

    url = build_url(place_id)
    playwright = await async_playwright().start()

    proxy = proxy_manager.get_proxy()

    # 🔥 Headless/Headful switching
    headless_mode = random.choice([True, False])

    browser = await playwright.chromium.launch(
        headless=headless_mode,
        proxy={"server": proxy} if proxy else None
    )

    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS)
    )

    page = await context.new_page()
    await stealth_async(page)

    responses = []

    async def handle_response(response):
        try:
            if "batchexecute" in response.url:
                responses.append(await response.text())
        except:
            pass

    page.on("response", handle_response)

    try:
        await page.goto(url, timeout=60000)
        await page.wait_for_load_state("domcontentloaded")

        content = await page.content()

        # 🔥 BLOCK DETECTION
        if is_blocked(content):
            print("🚫 Block detected, retrying...")
            proxy_manager.mark_failure(proxy)
            await browser.close()
            await playwright.stop()
            return []

        # Consent
        try:
            await page.click("button:has-text('I agree')", timeout=5000)
        except:
            pass

        await simulate_human(page)

        # 🔥 AUTO PAGINATION
        await auto_scroll(page, limit)

        await asyncio.sleep(3)

        await browser.close()
        await playwright.stop()

        all_reviews = []
        for r in responses:
            all_reviews.extend(parse_batchexecute(r))

        if all_reviews:
            proxy_manager.mark_success(proxy)
        else:
            proxy_manager.mark_failure(proxy)

        return all_reviews[:limit]

    except Exception as e:
        print("❌ Scrape error:", e)
        proxy_manager.mark_failure(proxy)

        await browser.close()
        await playwright.stop()

        return []

# ==========================================
# 🔥 WORKER SYSTEM
# ==========================================

async def worker(queue: asyncio.Queue, results: List, limit: int):
    while not queue.empty():
        place_id = await queue.get()

        try:
            data = await run_scrape(place_id, limit)
            if data:
                results.extend(data)
        except Exception as e:
            print("Worker error:", e)
        finally:
            queue.task_done()

# ==========================================
# 🔥 MAIN ENGINE
# ==========================================

async def scrape_engine(place_id: str, limit: int):

    queue = asyncio.Queue()

    for _ in range(MAX_RETRIES):
        await queue.put(place_id)

    results = []

    workers = [
        asyncio.create_task(worker(queue, results, limit))
        for _ in range(MAX_WORKERS)
    ]

    await queue.join()

    for w in workers:
        w.cancel()

    # Deduplicate
    unique = {
        f"{r['author_name']}_{r['text'][:50]}": r
        for r in results
    }.values()

    return list(unique)[:limit]

# ==========================================
# 🔥 PUBLIC FUNCTION (ALIGNED WITH YOUR PROJECT)
# ==========================================

async def fetch_reviews(place_id: str, limit: int = 100):
    return await scrape_engine(place_id, limit)

# ==========================================
print("✅ PRO scraper loaded (Scrapeless-level engine)")
