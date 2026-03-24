import asyncio
import json
import re
import random
import logging
from patchright.async_api import async_playwright
from playwright_stealth import stealth_async

# Configure logging for Railway Deploy Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.scraper")

async def fetch_reviews(place_id: str, limit: int = 50):
    """
    STRICT PATCHRIGHT + WEBSHARE PROXY + COOKIE BYPASS:
    The complete logic to bypass Google's 2026 security layers.
    """
    
    # 🌐 YOUR WEBSHARE PROXIES (from image_f1949d.jpg)
    PROXIES = [
        "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
        "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
        "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
        "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
        "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
    ]
    
    selected_proxy = random.choice(PROXIES)

    async with async_playwright() as p:
        logger.info(f"🎭 Launching Patchright (Stealth Engine)...")
        logger.info(f"📡 Routing through Proxy: {selected_proxy.split('@')[-1]}")

        # Launch with Patchright binary to hide 'webdriver' flags
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": selected_proxy},
            args=[
                "--disable-dev-shm-usage", 
                "--no-sandbox",
                "--disable-gpu",
                "--single-process"
            ]
        )

        # Desktop Context to appear more 'trustworthy' to Google
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )

        page = await context.new_page()
        
        # Apply stealth_async to handle secondary fingerprinting (canvas, plugins, etc.)
        await stealth_async(page)

        captured_reviews = []

        # 🔍 THE VIDEO METHOD: Intercept the 'batchexecute' background stream
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    # Clean Google's JSON protection prefix
                    clean_text = text.replace(")]}'", "").strip()
                    
                    # 'wrb.fr' is the key identifier for Map review data
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', clean_text)
                    for m in matches:
                        raw_data = json.loads(m)
                        inner_data = json.loads(raw_data[2])
                        for block in inner_data:
                            for r in block:
                                try:
                                    if r[0] and r[3]:
                                        captured_reviews.append({
                                            "review_id": r[0],
                                            "author": r[1][0],
                                            "rating": r[4],
                                            "text": r[3],
                                            "date": r[14]
                                        })
                                except: continue
                except: pass

        page.on("response", handle_response)

        try:
            # Add &hl=en to ensure the 'Accept' button is in English for our clicker
            url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}&hl=en"
            
            logger.info(f"🌐 Navigating to Map...")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # 🍪 COOKIE BYPASS: Google shows a consent page for UK/US proxies
            try:
                # Look for 'Accept all' or 'Agree' button
                accept_button = page.get_by_role("button", name=re.compile("Accept all|Agree|Allow", re.IGNORECASE))
                if await accept_button.is_visible(timeout=7000):
                    await accept_button.click()
                    logger.info("🍪 Cookie Consent Bypassed.")
                    # Give it a moment to redirect back to the map
                    await asyncio.sleep(3)
            except Exception:
                logger.info("🍪 No Cookie popup detected, proceeding...")

            # Wait for the review container to actually exist before scrolling
            await asyncio.sleep(5) 

            logger.info("🖱️ Scrolling to trigger background data...")
            for i in range(15): 
                # Scroll within the viewport
                await page.mouse.wheel(0, random.randint(1500, 2500))
                
                # Human-like delay to let the proxy load the next batch of data
                await asyncio.sleep(random.uniform(4.0, 8.0))
                
                if len(captured_reviews) >= limit:
                    break

            await browser.close()
            
            # Deduplicate by unique review_id
            unique_reviews = {r['review_id']: r for r in captured_reviews}
            final_list = list(unique_reviews.values())
            
            logger.info(f"✅ Mission Success: {len(final_list)} reviews captured.")
            return final_list[:limit]

        except Exception as e:
            logger.error(f"❌ Patchright Error: {str(e)}")
            if 'browser' in locals():
                await browser.close()
            return []
