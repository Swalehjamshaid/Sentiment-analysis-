import asyncio
import json
import random
import re
import logging
from patchright.async_api import async_playwright
from playwright_stealth import stealth_async

# Configure logging to see progress in Railway Deploy Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.scraper")

async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Optimized for Railway. Uses Patchright to bypass Google detection.
    """
    # ⚠️ IF YOU STILL GET 0 REVIEWS: Google has blocked the Railway IP.
    # You will need to uncomment the proxy lines below.
    # PROXY_SERVER = "http://your-proxy-address:port" 

    async with async_playwright() as p:
        logger.info("🚀 Launching Patchright Browser...")
        
        # 1. Resource-efficient launch
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage", 
                "--no-sandbox",
                "--disable-gpu",
                "--single-process" 
            ]
            # , proxy={"server": PROXY_SERVER} 
        )

        # 2. Advanced Stealth Context
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )

        page = await context.new_page()
        await stealth_async(page)

        captured_reviews = []

        # 3. Intercept API responses (Faster & Harder to block than HTML scraping)
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    # Extract review data from Google's internal JSON stream
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', text)
                    for m in matches:
                        data = json.loads(json.loads(m)[2])
                        for block in data:
                            for r in block:
                                try:
                                    captured_reviews.append({
                                        "author": r[1][0],
                                        "rating": r[4],
                                        "text": r[3] or "No text provided",
                                        "date": r[14]
                                    })
                                except: continue
                except: pass

        page.on("response", handle_response)

        try:
            # 4. Use a direct mobile-friendly Google Maps URL
            url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
            
            logger.info(f"🌐 Navigating to place: {place_id}")
            # Failsafe timeout to prevent 'Stuck' state
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # 5. Simulated Human Interaction
            logger.info("🖱️ Scrolling for reviews...")
            for i in range(5):
                await page.mouse.wheel(0, 1500)
                await asyncio.sleep(random.uniform(1.5, 3.0))
                if len(captured_reviews) >= limit: break

            await browser.close()
            
            # Remove duplicates
            unique_reviews = [dict(t) for t in {tuple(d.items()) for d in captured_reviews}]
            logger.info(f"✅ Successfully found {len(unique_reviews)} reviews.")
            return unique_reviews[:limit]

        except Exception as e:
            logger.error(f"❌ Scraper stopped: {str(e)}")
            if 'browser' in locals(): await browser.close()
            return []
