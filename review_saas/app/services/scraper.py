import asyncio
import json
import re
import random
import logging
from patchright.async_api import async_playwright
from playwright_stealth import stealth_async

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.scraper")

async def get_free_proxies():
    """
    Optional: You can add logic here to fetch real-time free proxies.
    For now, we will use a placeholder or manual list.
    """
    # Example: ['http://ip:port', 'http://ip:port']
    return [] 

async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Full implementation of the Thomas Janssen 'Network Interception' logic
    with added support for Free Proxies and increased human-like delays.
    """
    
    # 🕵️ FREE PROXY LOGIC
    # Note: Free proxies are often slow. We use a long timeout.
    proxies = await get_free_proxies()
    proxy_to_use = random.choice(proxies) if proxies else None

    async with async_playwright() as p:
        logger.info("🎭 Launching Patchright Browser (Stealth Mode)...")
        
        launch_args = [
            "--disable-dev-shm-usage", 
            "--no-sandbox",
            "--disable-gpu",
            "--single-process",
            "--disable-blink-features=AutomationControlled"
        ]

        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": proxy_to_use} if proxy_to_use else None,
            args=launch_args
        )

        # 📱 Mobile Emulation (Google is less suspicious of mobile users)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
            viewport={"width": 393, "height": 852},
            is_mobile=True,
            has_touch=True
        )

        page = await context.new_page()
        await stealth_async(page)

        captured_reviews = []

        # 🔍 THE VIDEO LOGIC: Intercepting the 'batchexecute' data stream
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    clean_text = text.replace(")]}'", "").strip()
                    
                    # 'wrb.fr' is the internal identifier for Google Maps review data
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', clean_text)
                    for m in matches:
                        raw_data = json.loads(m)
                        inner_data = json.loads(raw_data[2])
                        
                        for block in inner_data:
                            for r in block:
                                try:
                                    captured_reviews.append({
                                        "review_id": r[0],
                                        "author": r[1][0],
                                        "rating": r[4],
                                        "text": r[3] or "No text",
                                        "date": r[14]
                                    })
                                except:
                                    continue
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            # Construct direct Maps reviews URL
            url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
            
            logger.info(f"🌐 Navigating to Map Data for ID: {place_id}")
            # Increased timeout for slow free proxies
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)

            # 🖱️ SLOW HUMAN SCROLLING (Crucial for Cloud Servers)
            # We scroll more slowly to make the Singapore IP look more like a browsing human
            logger.info("🖱️ Scrolling slowly to mimic human reading...")
            for i in range(15): 
                await page.mouse.wheel(0, random.randint(1000, 2000))
                
                # Randomized long pauses (4 to 8 seconds)
                sleep_time = random.uniform(4.0, 8.0)
                await asyncio.sleep(sleep_time)
                
                if len(captured_reviews) >= limit:
                    break

            await browser.close()
            
            # Deduplicate
            unique_reviews = {r['review_id']: r for r in captured_reviews}
            final_list = list(unique_reviews.values())
            
            logger.info(f"✅ Success! Found {len(final_list)} reviews.")
            return final_list[:limit]

        except Exception as e:
            logger.error(f"❌ Scraper Error: {str(e)}")
            if 'browser' in locals():
                await browser.close()
            return []
