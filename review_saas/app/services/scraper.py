import asyncio
import random
import json
import re
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

MAX_RETRIES = 3

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119 Safari/537.36",
]


# ==========================================
# PARSE BATCHEXECUTE RESPONSE
# ==========================================

def parse_batchexecute(text):
    try:
        # Remove Google's anti-JSON prefix
        cleaned = text.replace(")]}'", "")

        # Extract JSON string inside
        matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned)

        all_reviews = []

        for match in matches:
            try:
                data = json.loads(match)

                # Deep nested extraction (Google format)
                payload = data[2]

                if isinstance(payload, str):
                    inner = json.loads(payload)

                    for block in inner:
                        for review in block:
                            try:
                                review_text = review[3]
                                rating = review[4]
                                author = review[0][1]

                                all_reviews.append({
                                    "author": author,
                                    "rating": rating,
                                    "text": review_text
                                })
                            except:
                                continue
            except:
                continue

        return all_reviews

    except Exception as e:
        print("Parse Error:", e)
        return []


# ==========================================
# SCRAPER
# ==========================================

async def scrape_google_reviews(url):

    for attempt in range(MAX_RETRIES):

        print(f"\n🚀 Attempt {attempt+1}")

        async with async_playwright() as p:

            browser = await p.chromium.launch(headless=True)

            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS)
            )

            page = await context.new_page()
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

                await page.wait_for_load_state("networkidle")

                # Scroll to load reviews
                for _ in range(6):
                    await page.mouse.wheel(0, 4000)
                    await asyncio.sleep(2)

                await asyncio.sleep(5)

                await browser.close()

                # ==================================
                # PARSE REVIEWS
                # ==================================
                all_reviews = []

                for raw in batchexecute_data:
                    parsed = parse_batchexecute(raw)
                    all_reviews.extend(parsed)

                return {
                    "success": True,
                    "total_reviews_found": len(all_reviews),
                    "reviews": all_reviews[:20]  # preview
                }

            except Exception as e:
                print("Error:", e)
                await browser.close()
                await asyncio.sleep(2)

    return {"success": False}


# ==========================================
# RUN
# ==========================================

if __name__ == "__main__":

    url = input("Enter Google Maps URL: ").strip()

    result = asyncio.run(scrape_google_reviews(url))

    print("\n========== RESULT ==========")
    print(json.dumps(result, indent=2))
