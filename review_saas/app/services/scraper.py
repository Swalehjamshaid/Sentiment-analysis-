import asyncio
import json
import re
import random
import logging
from patchright.async_api import async_playwright
from playwright_stealth import stealth_async

# Configure logging to see progress in your Railway Deploy Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.scraper")

async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Extracts Google Reviews by intercepting internal JSON streams (batchexecute).
    Optimized for Patchright and Railway deployment.
    """
    
    # 🌐 PROXY CONFIGURATION (Highly Recommended for Railway)
    # If you still get 0 reviews, uncomment and fill in your proxy details.
    # PROXY = {
    #     "server": "http://your-proxy-address:port",
    #     "username": "your-username",
    #     "password": "your-password"
    # }

    async with async_playwright() as p:
        logger.info("🎭 Launching Patchright Browser in Stealth Mode...")
        
        # Launch using Patchright's undetected binary
        browser = await p.chromium.launch(
            headless=True,
            # proxy=PROXY,  # Uncomment this line when you have a proxy
            args=[
                "--disable-dev-shm-usage", 
                "--no-sandbox",
                "--disable-gpu",
                "--single-process",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        # Create a realistic browser context
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )

        page = await context.new_page()
        
        # Apply the stealth patches to hide the 'webdriver' flags
        await stealth_async(page)

        captured_reviews = []

        # 🔍 THE VIDEO LOGIC: Intercepting the 'batchexecute' data stream
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    # Google prefixes their JSON with specific security characters
                    clean_text = text.replace(")]}'", "").strip()
                    
                    # Find review blocks using the internal Google 'wrb.fr' identifier
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', clean_text)
                    for m in matches:
                        # Google uses nested JSON strings
                        raw_data = json.loads(m)
                        inner_data = json.loads(raw_data[2])
                        
                        for block in inner_data:
                            # Iterate through the review objects in the data stream
                            for r in block:
                                try:
                                    captured_reviews.append({
                                        "review_id": r[0],
                                        "author": r[1][0],
                                        "rating": r[4],
                                        "text": r[3] or "No text provided",
                                        "date": r[14],
                                        "profile_photo": r[1][1]
                                    })
                                except (IndexError, TypeError):
                                    continue
                except Exception:
                    pass

        # Attach the listener to the page
        page.on("response", handle_response)

        try:
            # Construct a direct URL to the reviews section
            # This specific URL structure is often more successful for scraping
            url = f"https://www.google.com/maps/preview/review/listentities?authuser=0&hl=en&gl=us&pb=!1m2!1y{place_id}!2y{place_id}"
            
            # Alternatively, use the standard Maps URL if the above is blocked
            maps_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
            
            logger.info(f"🌐 Navigating to place reviews: {place_id}")
            await page.goto(maps_url, wait_until="domcontentloaded", timeout=60000)

            # 🖱️ Simulated Human Interaction
            # We scroll to trigger the API calls that our listener captures
            logger.info("🖱️ Scrolling to trigger Google API responses...")
            for i in range(12): 
                await page.mouse.wheel(0, 2500)
                # Random delays mimic a human reading the reviews
                await asyncio.sleep(random.uniform(2.0, 4.0))
                
                if len(captured_reviews) >= limit:
                    logger.info(f"✨ Goal reached: {len(captured_reviews)} reviews captured.")
                    break

            await browser.close()
            
            # Deduplicate the list using the unique review_id
            unique_reviews = {r['review_id']: r for r in captured_reviews}
            final_list = list(unique_reviews.values())
            
            logger.info(f"✅ Success! Total reviews extracted: {len(final_list)}")
            return final_list[:limit]

        except Exception as e:
            logger.error(f"❌ Scraper Error: {str(e)}")
            if 'browser' in locals():
                await browser.close()
            return []

# For testing locally:
# if __name__ == "__main__":
#     # Salt'n Pepper Village Lahore Place ID
#     asyncio.run(fetch_reviews("ChIJDVYKpFEEGTkRp_XASXZ21Tc"))
