import httpx
import logging
import re
import random
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright

logger = logging.getLogger("scraper")

# =====================================================
# 🌍 CONFIG
# =====================================================

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 Chrome/122 Mobile",
    "Mozilla/5.0 (Linux; Android 13; Samsung Galaxy S23) AppleWebKit/537.36 Chrome/120 Mobile",
    "Mozilla/5.0 (Linux; Android 12; Pixel 7) AppleWebKit/537.36 Chrome/118 Mobile",
]

PROXIES = [
    # "http://user:pass@host:port"
]

# =====================================================
# 🧩 HELPERS
# =====================================================

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-PK,en-US;q=0.9",
        "Sec-CH-UA-Mobile": "?1",
        "Sec-CH-UA-Platform": '"Android"',
        "Referer": "https://www.google.com/",
        "X-Requested-With": "com.android.chrome"
    }


def get_proxy():
    return random.choice(PROXIES) if PROXIES else None


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^<]+?>', '', text)
    return " ".join(text.split())


# =====================================================
# 🔁 SAFE HTTP REQUEST
# =====================================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2))
async def safe_request(url, headers, proxy):
    async with httpx.AsyncClient(
        headers=headers,
        timeout=30.0,
        proxies=proxy,
        follow_redirects=True
    ) as client:
        return await client.get(url)


# =====================================================
# 🔍 EXTRACTION STRATEGIES
# =====================================================

def extract_strategy_1(html):
    """Primary: data-review-id"""
    return re.findall(
        r'data-review-id="(Ch[a-zA-Z0-9_-]{16,})".*?aria-label="([\d]).*?stars".*?<span>(.*?)</span>',
        html,
        re.DOTALL
    )


def extract_strategy_2(html):
    """Secondary: aria stars pattern"""
    return re.findall(
        r'aria-label="([\d]\.[\d]) stars".*?<span>(.*?)</span>',
        html,
        re.DOTALL
    )


def extract_strategy_3(html):
    """Short text snippets"""
    return re.findall(
        r'<span>([^<]{40,300})</span>',
        html
    )


def extract_strategy_4(html):
    """Review IDs fallback"""
    return re.findall(r'Ch[a-zA-Z0-9_-]{18,22}', html)


def extract_strategy_5(html):
    """Loose star detection"""
    return re.findall(
        r'([\d]) star.*?<span>(.*?)</span>',
        html,
        re.DOTALL
    )


# =====================================================
# 🌐 HTTP SCRAPER (MULTI-STRATEGY)
# =====================================================

async def http_scrape(place_id, limit):
    logger.info("🌐 HTTP scraping started")

    queries = [
        f"https://www.google.com/search?q=reviews+for+{place_id}&hl=en&gl=pk",
        f"https://www.google.com/search?q={place_id}+reviews",
        f"https://www.google.com/search?q={place_id}+rating",
    ]

    all_reviews = []

    for url in queries:
        try:
            headers = get_headers()
            proxy = get_proxy()

            res = await safe_request(url, headers, proxy)

            if res.status_code != 200:
                continue

            html = res.text

            # Apply all strategies
            strategies = [
                ("S1", extract_strategy_1(html)),
                ("S2", extract_strategy_2(html)),
                ("S3", extract_strategy_3(html)),
                ("S4", extract_strategy_4(html)),
                ("S5", extract_strategy_5(html)),
            ]

            for label, matches in strategies:
                for i, item in enumerate(matches):
                    if len(all_reviews) >= limit:
                        break

                    if isinstance(item, tuple):
                        rating = int(item[0][0]) if item[0][0].isdigit() else 5
                        text = item[1] if len(item) > 1 else str(item)
                    else:
                        rating = 5
                        text = item

                    text = clean_text(text)

                    if len(text) > 10:
                        all_reviews.append({
                            "review_id": f"{label}_{i}_{random.randint(1000,9999)}",
                            "rating": rating,
                            "text": text,
                            "method": f"HTTP_{label}",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })

            if all_reviews:
                logger.info(f"✅ HTTP Success: {len(all_reviews)}")
                return all_reviews

        except Exception as e:
            logger.warning(f"⚠️ HTTP error: {e}")

    return []


# =====================================================
# 🖥️ PLAYWRIGHT FALLBACK
# =====================================================

async def playwright_scrape(place_id, limit):
    logger.info("🖥️ Playwright fallback started")

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS)
        )

        page = await context.new_page()

        await page.goto(f"https://www.google.com/maps/place/?q=place_id:{place_id}")
        await asyncio.sleep(5)

        # Open reviews
        selectors = [
            'button[jsaction*="pane.reviewChart.moreReviews"]',
            'button:has-text("reviews")'
        ]

        for sel in selectors:
            try:
                await page.click(sel)
                break
            except:
                continue

        await asyncio.sleep(5)

        # Scroll
        for _ in range(20):
            await page.mouse.wheel(0, 4000)
            await asyncio.sleep(1)

        cards = await page.query_selector_all('div[data-review-id]')

        for c in cards:
            try:
                rid = await c.get_attribute("data-review-id")

                rating_el = await c.query_selector('span[aria-label*="stars"]')
                rating = int((await rating_el.get_attribute("aria-label"))[0]) if rating_el else 5

                text_el = await c.query_selector('span[jsname="fbQN7e"]') or \
                          await c.query_selector('span[jsname="bN97Pc"]')

                text = await text_el.inner_text() if text_el else ""

                if text:
                    results.append({
                        "review_id": rid,
                        "rating": rating,
                        "text": clean_text(text),
                        "method": "PLAYWRIGHT",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

            except:
                continue

        await browser.close()

    logger.info(f"✅ Playwright Success: {len(results)}")
    return results[:limit]


# =====================================================
# 🚀 MAIN FUNCTION
# =====================================================

async def fetch_reviews(place_id: str, limit: int = 100):

    # 🔥 Step 1: HTTP attempts
    reviews = await http_scrape(place_id, limit)

    if reviews:
        return reviews[:limit]

    # 🔥 Step 2: Playwright fallback
    reviews = await playwright_scrape(place_id, limit)

    if reviews:
        return reviews[:limit]

    logger.error("💀 ALL METHODS FAILED")
    return []
