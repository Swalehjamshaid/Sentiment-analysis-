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

async def fetch_reviews(place_id: str, limit: int = 50):
    """
    STRICT PATCHRIGHT + WEBSHARE PROXY + DEEP WAIT:
    Forces the browser to wait for the UI to load before scrolling.
    """
    
    # YOUR WEBSHARE PROXIES (from image_f1949d.jpg)
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

        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": selected_proxy},
            args=["--no-sandbox", "--disable-gpu", "--single-process"]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )

        page = await context.new_page()
        await stealth_async(page)

        captured_reviews = []

        # Intercept the background data stream (The Video Method)
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    clean_text = text.replace(")]}'", "").strip()
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
            # hl=en forces English buttons, gl=us matches your proxy country to avoid blocks
            url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}&hl=en"
            
            logger.info(f"🌐 Navigating to Map...")
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # 🍪 STEP 1: Handle Cookie Consent (Common for UK/US Proxies)
            try:
                # Wait for the 'Accept' button to appear
                consent_button = page.locator('button:has-text("Accept all"), button:has-text("Agree")')
                if await consent_button.is_visible(timeout=5000):
                    await consent_button.click()
                    logger.info("🍪 Cookie popup bypassed.")
                    await asyncio.sleep(2)
            except: pass

            # ⏳ STEP 2: THE CRITICAL WAIT (Why it was returning 0)
            # We wait until at least ONE review star or text block is visible on the screen.
            logger.info("⏳ Waiting for reviews to appear in UI...")
            try:
                # This selector looks for the review text area
                await page.wait_for_selector('.wiI7eb', timeout=15000)
                logger.info("✅ Reviews detected in UI. Starting scroll.")
            except:
                logger.warning("🕒 UI slow to load. Proceeding with blind scroll.")

            # 🖱️ STEP 3: HUMAN SCROLLING
            for i in range(15): 
                # Hover over the review pane before scrolling
                await page.mouse.move(400, 400)
                await page.mouse.wheel(0, 2000)
                
                # Randomized long pause to let the proxy catch up
                await asyncio.sleep(random.uniform(4.0, 8.0))
                
                if len(captured_reviews) >= limit:
                    break

            await browser.close()
            
            unique_reviews = {r['review_id']: r for r in captured_reviews}
            final_list = list(unique_reviews.values())
            
            logger.info(f"✅ Mission Success: {len(final_list)} reviews captured.")
            return final_list[:limit]

        except Exception as e:
            logger.error(f"❌ Patchright Error: {str(e)}")
            if 'browser' in locals(): await browser.close()
            return []
