import asyncio
import json
import re
import random
import logging
from patchright.async_api import async_playwright
from playwright_stealth import stealth_async

logger = logging.getLogger("app.scraper")

async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Uses the exact 'Network Interception' logic from the video to 
    capture Google's internal 'batchexecute' stream.
    """
    async with async_playwright() as p:
        logger.info("🚀 Launching Patchright Browser (Stealth Mode)...")
        
        # 1. Launch with stealth-optimized args
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage", 
                "--no-sandbox",
                "--disable-gpu",
                "--single-process"
            ]
        )

        # 2. Set a real-world User Agent
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        page = await context.new_page()
        await stealth_async(page) # Apply the stealth patches

        captured_reviews = []

        # 3. THE VIDEO LOGIC: Intercept the 'batchexecute' JSON stream
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    # Clean the Google prefix
                    clean_text = text.replace(")]}'", "").strip()
                    # Find the review data patterns (wrb.fr is the internal Google Maps code)
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', clean_text)
                    for m in matches:
                        # Double JSON load is required for Google's nested format
                        data = json.loads(json.loads(m)[2])
                        for block in data:
                            for r in block:
                                try:
                                    captured_reviews.append({
                                        "author": r[1][0],
                                        "rating": r[4],
                                        "text": r[3] or "No comment",
                                        "date": r[14],
                                        "review_id": r[0]
                                    })
                                except (IndexError, TypeError):
                                    continue
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            # 4. Navigate to the Google Reviews URL
            # Using the mobile-style link often bypasses more checks
            url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
            
            logger.info(f"🌐 Navigating to Maps...")
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # 5. Simulate human scrolling to trigger the API calls
            logger.info("🖱️ Scrolling to trigger data stream...")
            for i in range(10): # Scroll 10 times to get more reviews
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(random.uniform(1.5, 3.0))
                if len(captured_reviews) >= limit:
                    break

            await browser.close()
            
            # 6. Deduplicate by Review ID
            unique_reviews = {r['review_id']: r for r in captured_reviews}
            final_list = list(unique_reviews.values())
            
            logger.info(f"✅ Successfully extracted {len(final_list)} reviews.")
            return final_list[:limit]

        except Exception as e:
            logger.error(f"❌ Scraper Failure: {str(e)}")
            if 'browser' in locals(): await browser.close()
            return []
