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

MAX_RETRIES = 5
SCROLL_STEPS = 8

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/119 Safari/537.36",
]

# 🔥 ADD YOUR REAL PROXIES HERE
PROXIES = [
    None,
    # "http://user:pass@ip1:port",
    # "http://user:pass@ip2:port",
]

SESSION_FILE = "session.json"


# ==========================================
# HUMAN SIMULATION
# ==========================================

async def simulate_human(page):
    for _ in range(5):
        await page.mouse.move(
            random.randint(100, 900),
            random.randint(100, 700)
        )
        await asyncio.sleep(random.uniform(0.3, 1.2))

    for _ in range(SCROLL_STEPS):
        await page.mouse.wheel(0, random.randint(2000, 4000))
        await asyncio.sleep(random.uniform(1.5, 3))


# ==========================================
# PARSER (Google batchexecute)
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

    except:
        return []


# ==========================================
# ENGINE CLASS
# ==========================================

class ScrapelessEngine:

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None

    async def init_browser(self):
        self.playwright = await async_playwright().start()

        proxy = random.choice(PROXIES)

        self.browser = await self.playwright.chromium.launch(
            headless=True,
            proxy={"server": proxy} if proxy else None
        )

        try:
            self.context = await self.browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                storage_state=SESSION_FILE
            )
        except:
            self.context = await self.browser.new_context(
                user_agent=random.choice(USER_AGENTS)
            )

    async def close(self):
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except:
            pass

    async def run_single(self, url: str) -> List[Dict]:

        await self.init_browser()

        page = await self.context.new_page()
        await stealth_async(page)

        batchexecute_data = []

        async def handle_response(response):
            try:
                if "batchexecute" in response.url:
                    text = await response.text()
                    batchexecute_data.append(text)
            except:
                pass

        page.on("response", handle_response)

        try:
            await page.goto(url, timeout=60000)
            await page.wait_for_load_state("domcontentloaded")

            # Handle consent
            try:
                await page.click("button:has-text('I agree')", timeout=5000)
            except:
                pass

            # Simulate human
            await simulate_human(page)

            await asyncio.sleep(4)

            # Save session
            try:
                await self.context.storage_state(path=SESSION_FILE)
            except:
                pass

            await self.close()

            # Parse
            all_reviews = []
            for raw in batchexecute_data:
                all_reviews.extend(parse_batchexecute(raw))

            return all_reviews

        except Exception as e:
            print("❌ Run Error:", e)
            await self.close()
            return []

    async def scrape(self, url: str) -> Dict[str, Any]:

        all_results = []

        for attempt in range(MAX_RETRIES):
            print(f"🚀 Attempt {attempt+1}")

            results = await self.run_single(url)

            if results:
                all_results.extend(results)

                # If enough data found, stop early
                if len(all_results) > 20:
                    break

            await asyncio.sleep(2)

        # Remove duplicates
        unique_reviews = {r["text"]: r for r in all_results}.values()

        return {
            "success": len(unique_reviews) > 0,
            "count": len(unique_reviews),
            "reviews": list(unique_reviews)[:50]
        }


# ==========================================
# PUBLIC FUNCTION
# ==========================================

async def scrape_google_reviews(url: str):
    engine = ScrapelessEngine()
    return await engine.scrape(url)
