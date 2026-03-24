import asyncio
import random
import json
from typing import Dict, List
from playwright.async_api import async_playwright

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Linux; Android 14)"
]

def clean(text):
    return " ".join(text.split()) if text else ""

# ✅ PARSER
def parse_reviews(raw: str) -> List[Dict]:
    reviews = []

    try:
        if raw.startswith(")]}'"):
            raw = raw[4:]

        data = json.loads(raw)

        if len(data) < 3:
            return []

        for r in data[2]:
            try:
                reviews.append({
                    "review_id": r[0],
                    "author": r[1][0] if r[1] else "Anonymous",
                    "rating": r[4],
                    "text": clean(r[3])
                })
            except:
                continue

    except:
        pass

    return reviews


async def fetch_reviews(place_id: str, limit: int = 500):

    collected = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS)
        )

        page = await context.new_page()

        # 🔥 CAPTURE API
        async def handle_response(response):
            try:
                if "listentitiesreviews" in response.url:
                    raw = await response.text()

                    parsed = parse_reviews(raw)

                    for r in parsed:
                        collected[r["review_id"]] = r

            except:
                pass

        page.on("response", handle_response)

        # 🌍 Open Maps
        await page.goto(
            f"https://www.google.com/maps/place/?q=place_id:{place_id}",
            timeout=120000,
            wait_until="domcontentloaded"
        )

        await asyncio.sleep(5)

        # 🔥 IMPORTANT: Click rating (THIS TRIGGERS API)
        clicked = False

        selectors = [
            'button[jsaction*="pane.reviewChart.moreReviews"]',
            'button[jsaction*="pane.reviewChart.openReviews"]',
            'button:has-text("reviews")',
            'button:has-text("Review")',
            'span[role="img"]'
        ]

        for sel in selectors:
            try:
                await page.click(sel, timeout=5000)
                clicked = True
                break
            except:
                continue

        if not clicked:
            print("❌ Could not trigger reviews API")
            await browser.close()
            return []

        await asyncio.sleep(5)

        # 🔥 SCROLL AFTER OPENING REVIEWS
        for _ in range(25):
            await page.mouse.wheel(0, 5000)
            await asyncio.sleep(random.uniform(1.5, 3))

        await browser.close()

    print(f"✅ Reviews collected: {len(collected)}")

    return list(collected.values())[:limit]


# 🚀 TEST
if __name__ == "__main__":
    data = asyncio.run(fetch_reviews("ChIJ8S6kk9YJGTkRWK6XHzCKSrA"))
    print(len(data))
