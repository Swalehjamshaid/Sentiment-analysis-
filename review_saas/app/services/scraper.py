import asyncio
import json
import re
import random
import logging
import os
import urllib.parse
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ReviewSaaS.Scraper")

API_TOKEN = os.getenv("SCRAPE_DO_TOKEN")
sem = asyncio.Semaphore(5)

async def fetch_reviews(place_id: str, limit: int = 5):
    async with sem:
        logger.info(f"🚀 [Railway] Starting 5-Review Scraper for: {place_id}")
        
        if not API_TOKEN:
            logger.error("❌ SCRAPE_DO_TOKEN missing!")
            return []

        reviews_data = []
        visited_ids = set()
        target_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
        encoded_url = urllib.parse.quote(target_url)
        scrape_do_gateway = f"https://api.scrape.do?token={API_TOKEN}&url={encoded_url}&render=true"

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
                context = await browser.new_context(viewport={'width': 1280, 'height': 800})
                page = await context.new_page()
                await stealth_async(page)

                async def handle_response(response):
                    if len(reviews_data) >= limit: return
                    if "batchexecute" in response.url:
                        try:
                            text = await response.text()
                            cleaned = text.replace(")]}'", "").strip()
                            matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned)
                            for match in matches:
                                inner = json.loads(json.loads(match)[2])
                                for block in [b for b in inner if isinstance(b, list)]:
                                    for r in block:
                                        try:
                                            r_id = r[0]
                                            if r_id not in visited_ids and len(reviews_data) < limit:
                                                reviews_data.append({
                                                    "review_id": r_id,
                                                    "author_name": r[1][0],
                                                    "rating": r[4],
                                                    "text": r[3] or "No text content",
                                                    "scraped_at": datetime.utcnow().isoformat()
                                                })
                                                visited_ids.add(r_id)
                                                logger.info(f"✨ Captured Review {len(reviews_data)}")
                                        except: continue
                        except: pass

                page.on("response", handle_response)

                logger.info("📡 Navigating via Scrape.do API...")
                await page.goto(scrape_do_gateway, wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(8000) # Wait for page to settle

                # --- NEW UNIVERSAL CLICK LOGIC ---
                logger.info("🖱️ Hunting for Reviews tab...")
                # We try 3 different ways to find the button
                selectors = [
                    'button[aria-label*="Reviews"]', 
                    'button:has-text("Reviews")',
                    'div[role="tab"]:has-text("Reviews")'
                ]
                
                clicked = False
                for selector in selectors:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible(timeout=5000):
                            await btn.click()
                            logger.info(f"✅ Clicked Reviews tab using: {selector}")
                            clicked = True
                            break
                    except: continue
                
                if not clicked:
                    logger.warning("⚠️ Could not click tab, attempting force-scroll...")

                await page.wait_for_timeout(3000)

                # --- SCROLLING ---
                logger.info("🔄 Scrolling...")
                for i in range(5):
                    if len(reviews_data) >= limit: break
                    # Move mouse to the sidebar area and scroll
                    await page.mouse.move(400, 400)
                    await page.mouse.wheel(0, 3000)
                    await asyncio.sleep(random.uniform(4, 6))

            except Exception as e:
                logger.error(f"❌ Scraper failure: {str(e)}")
            finally:
                await browser.close()
                logger.info(f"✅ Scraping Complete. Total Found: {len(reviews_data)}")

        return reviews_data[:limit]

scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
