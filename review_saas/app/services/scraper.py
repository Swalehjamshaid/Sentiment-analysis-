import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 300, skip: int = 0) -> List[Dict[str, Any]]:
    reviews = []
    # Use the most direct Google Maps Search URL
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
            context = await browser.new_context(viewport={'width': 1280, 'height': 900})
            page = await context.new_page()
            
            logger.info(f"🚀 Navigating to Place ID: {place_id}")
            await page.goto(place_url, wait_until="domcontentloaded", timeout=60000)

            # --- THE CONSENT BREAKER ---
            try:
                # Look for "Accept all" or "Agree" buttons that block the view
                consent_btn = page.get_by_role("button", name=re.compile(r"Accept all|Agree|Allow", re.IGNORECASE)).first
                if await consent_btn.is_visible(timeout=5000):
                    await consent_btn.click()
                    logger.info("✅ Bypassed Google Consent Wall")
                    await page.wait_for_timeout(2000)
            except:
                logger.info("No consent wall detected, proceeding.")

            # --- TRIGGER REVIEWS PANEL ---
            try:
                # Try clicking the review count or the Reviews tab
                await page.get_by_role("button", name=re.compile(r"Reviews", re.IGNORECASE)).first.click()
                await page.wait_for_timeout(3000)
            except:
                logger.warning("Could not find Reviews button, trying direct scroll.")

            # --- TARGETED SCROLLING ---
            # We use a more flexible selector for the scrollable area
            scroll_selector = 'div[role="main"]'
            
            last_count = 0
            for i in range(30):
                # We scroll several different potential containers to be safe
                await page.evaluate('''
                    const containers = [
                        document.querySelector('div[role="main"] div[tabindex="-1"]'),
                        document.querySelector('div[role="main"]'),
                        window
                    ];
                    containers.forEach(c => { if(c) c.scrollTop += 5000; });
                ''')
                
                await page.wait_for_timeout(2000)
                
                # Search for review cards
                elements = await page.query_selector_all('div.jftiEf')
                current_count = len(elements)
                logger.info(f"🔄 Loop {i+1}: Found {current_count} reviews")
                
                if current_count >= limit: break
                if current_count == last_count and i > 10: break
                last_count = current_count

            # --- EXTRACTION ---
            final_elements = await page.query_selector_all('div.jftiEf')
            for r in final_elements[:limit]:
                try:
                    text_el = await r.query_selector('.wiI7pd')
                    author_el = await r.query_selector('.d4r55')
                    rating_el = await r.query_selector('span.kvMYJc')
                    
                    reviews.append({
                        "review_id": f"pw_{hash(str(datetime.now()))}_{len(reviews)}",
                        "rating": int((await rating_el.get_attribute("aria-label")).split()[0]) if rating_el else 0,
                        "text": await text_el.inner_text() if text_el else "No comment",
                        "author_name": await author_el.inner_text() if author_el else "Google User",
                        "google_review_time": datetime.utcnow().isoformat()
                    })
                except: continue
            
            await browser.close()
            logger.info(f"✨ MISSION COMPLETE: {len(reviews)} reviews ready for Postgres.")

    except Exception as e:
        logger.error(f"❌ Critical Failure: {str(e)}")
    
    return reviews
