import logging
import hashlib
import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

def parse_relative_date(date_text: str) -> datetime:
    """Universal date parser for relative strings."""
    now = datetime.utcnow()
    date_text = (date_text or "").lower()
    number = 1
    for part in date_text.split():
        if part.isdigit():
            number = int(part)
            break
    if "hour" in date_text: return now - timedelta(hours=number)
    if "day" in date_text: return now - timedelta(days=number)
    if "week" in date_text: return now - timedelta(weeks=number)
    if "month" in date_text: return now - timedelta(days=number * 30)
    if "year" in date_text: return now - timedelta(days=number * 365)
    return now

async def fetch_reviews(
    place_id: str,
    limit: int = 200,
    **kwargs
) -> List[Dict[str, Any]]:

    reviews: List[Dict[str, Any]] = []
    # 🎯 GLOBAL LOGIC: Direct 'lrd' URL format. 
    # This URL type is standardized by Google globally.
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            
            page = await context.new_page()
            logger.info(f"🌍 Global Sync Attempt: {place_id}")

            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # --- STEP 1: BYPASS ANY CONSENT (Global approach) ---
            try:
                # Instead of looking for "Accept", we click the primary action button
                await page.click('button[aria-haspopup="false"]:nth-child(2)', timeout=5000)
            except:
                pass

            # --- STEP 2: OPEN REVIEWS PANEL (Selector-based) ---
            try:
                # We click the star rating area, which is a universal link to reviews
                await page.click('span[role="img"][aria-label*="stars"]', timeout=10000)
                # Wait for the specific Material Design review container (jftiEf)
                await page.wait_for_selector('div.jftiEf', timeout=15000)
            except:
                logger.warning("⚠️ Could not trigger panel via stars, trying direct scroll.")

            collected_ids = set()
            scroll_attempts = 0
            
            while len(reviews) < limit and scroll_attempts < 50:
                # 1. Expand "More" (Using the jsname attribute which is global)
                mores = await page.query_selector_all('button[jsaction*="reviews.expand"]')
                for m in mores:
                    try: await m.click(timeout=500)
                    except: pass

                # 2. Extract Data using Permanent CSS Classes
                elements = await page.query_selector_all('div.jftiEf')
                if not elements and scroll_attempts > 10: break

                for r in elements:
                    try:
                        # Names, text, and dates always use these classes globally
                        author_el = await r.query_selector('.d4r55')
                        text_el = await r.query_selector('.wiI7pd')
                        date_el = await r.query_selector('.rsqaWe')
                        rating_el = await r.query_selector('span.kvMYJc')

                        author = await author_el.inner_text() if author_el else "User"
                        text = await text_el.inner_text() if text_el else ""
                        date_text = await date_el.inner_text() if date_el else ""
                        
                        review_id = hashlib.md5(f"{author}{text}".encode()).hexdigest()
                        if review_id in collected_ids: continue

                        rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                        rating = int(re.search(r'\d', rating_raw).group()) if re.search(r'\d', rating_raw) else 0

                        reviews.append({
                            "review_id": review_id,
                            "rating": rating,
                            "text": text,
                            "author_name": author,
                            "google_review_time": parse_relative_date(date_text).isoformat()
                        })
                        collected_ids.add(review_id)
                    except:
                        continue

                # 3. Targeted Scrolling (Center-Left Scroll)
                await page.mouse.move(400, 400)
                await page.mouse.wheel(0, 4000)
                await page.wait_for_timeout(2000)
                scroll_attempts += 1

            await browser.close()
            logger.info(f"✅ Success! Fetched {len(reviews)} reviews globally.")
            return reviews

    except Exception as e:
        logger.error(f"❌ Scraper Failure: {str(e)}")
        return []
