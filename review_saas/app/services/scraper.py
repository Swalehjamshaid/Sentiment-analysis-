import asyncio
import json
import random
import re
import logging
from patchright.async_api import async_playwright
from playwright_stealth import stealth_async

logger = logging.getLogger("app.scraper")

async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Optimized for Railway RAM limits and Google Anti-Bot.
    """
    # 🌐 CRITICAL: Google blocks Railway IPs. 
    # Use a Residential Proxy (SmartProxy, BrightData, or WebShare).
    # PROXY_URL = "http://username:password@proxy-provider.com:port"
    
    async with async_playwright() as p:
        # 1. Launch with 'headless_shell' for 40% less RAM usage
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage", # Prevent crashes on small Linux VMs
                "--no-sandbox",
                "--disable-gpu",
                "--single-process" # Saves RAM
            ]
            # , proxy={"server": PROXY_URL} # Uncomment this when you have a proxy
        )

        # 2. Emulate a Real Mobile Device
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
            viewport={"width": 393, "height": 852},
            is_mobile=True,
            has_touch=True
        )

        page = await context.new_page()
        await stealth_async(page)

        # 3. Intercept background data (more reliable than scraping HTML)
        captured_reviews = []
        
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    # Clean and find JSON blocks
                    clean_text = text.replace(")]}'", "").strip()
                    # Extract review patterns from the stream
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', clean_text)
                    for m in matches:
                        data = json.loads(json.loads(m)[2])
                        for block in data:
                            for r in block:
                                try:
                                    captured_reviews.append({
                                        "review_id": r[0],
                                        "author": r[1][0],
                                        "rating": r[4],
                                        "text": r[3] or "",
                                        "date": r[14]
                                    })
                                except: continue
                except: pass

        page.on("response", handle_response)

        try:
            # Construct Google Maps Search URL
            url = f"https://www.google.com/maps/search/?api=1&query={place_id}"
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # 4. Human-like Scrolling (Triggers the Data Stream)
            for _ in range(5):
                await page.mouse.wheel(0, random.randint(2000, 4000))
                await asyncio.sleep(random.uniform(2.0, 4.0))

            await browser.close()
            
            # Deduplicate
            unique_reviews = {r['review_id']: r for r in captured_reviews}
            final_list = list(unique_reviews.values())[:limit]
            
            logger.info(f"✅ Successfully fetched {len(final_list)} reviews.")
            return final_list

        except Exception as e:
            logger.error(f"❌ Scraper Error: {e}")
            if 'browser' in locals(): await browser.close()
            return []
