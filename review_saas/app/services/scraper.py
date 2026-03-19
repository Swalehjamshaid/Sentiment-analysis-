import logging
import hashlib
import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

def parse_relative_date(date_text: str) -> datetime:
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
    limit: int = 150,
    **kwargs
) -> List[Dict[str, Any]]:

    reviews: List[Dict[str, Any]] = []
    
    # NEW TECHNIQUE: The 'Preview' URL format. 
    # This forces a simplified 'Knowledge Card' view which is more stable for scraping.
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 1200}
            )
            
            page = await context.new_page()
            logger.info(f"🆕 New Technique Scrape: {place_id}")

            # 1. Direct Navigation with 'NetworkIdle' to ensure JS triggers are ready
            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # 2. Bypass Consent (Universal Selector)
            try:
                await page.click('button[aria-label*="Accept"], button:has-text("Accept")', timeout=5000)
            except:
                pass

            # 3. DIFFERENT LOGIC: Trigger reviews via the Rating Number
            # On many layouts, the rating number (e.g. 4.5) is a more stable link than the word "Reviews"
            try:
                # Find the rating span and click its parent
                rating_link = page.locator('span[aria-hidden="true"]').filter(has_text=re.compile(r"^\d\.\d$"))
                await rating_link.first.click(timeout=10000)
                await page.wait_for_timeout(3000)
            except:
                logger.warning("⚠️ Rating link click failed, trying secondary text trigger.")
                try:
                    await page.get_by_text(re.compile(r"\d+ reviews", re.IGNORECASE)).first.click(timeout=5000)
                except:
                    pass

            collected_ids = set()
            scroll_attempts = 0
            
            # 4. DATA EXTRACTION: Target by Attribute 'data-review-id'
            while len(reviews) < limit and scroll_attempts < 45:
                # Force "More" to expand
                mores = await page.query_selector_all('button[aria-label*="See more"]')
                for m in mores:
                    try: await m.click(timeout=300)
                    except: pass

                # The 'data-review-id' attribute is the most 'Solid' indicator of a review card
                elements = await page.query_selector_all('[data-review-id]')
                
                if not elements and scroll_attempts > 10:
                    break

                for r in elements:
                    try:
                        # Extract components using generic relative selectors
                        author_el = await r.query_selector('.d4r55')
                        text_el = await r.query_selector('.wiI7pd')
                        date_el = await r.query_selector('.rsqaWe')
                        rating_el = await r.query_selector('span.kvMYJc')

                        author = await author_el.inner_text() if author_el else "Guest"
                        text = await text_el.inner_text() if text_el else ""
                        date_text = await date_el.inner_text() if date_el else ""
                        
                        # Permanent Hash
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

                # 5. Different Scrolling Logic: Step-Scroll
                # Sometimes a massive wheel scroll causes Google to 'freeze' the page for bots.
                # We will do smaller, more frequent scrolls.
                await page.mouse.move(500, 500)
                for _ in range(5):
                    await page.mouse.wheel(0, 800)
                    await asyncio.sleep(0.4)
                
                scroll_attempts += 1

            await browser.close()
            logger.info(f"✅ New Technique Results: {len(reviews)} reviews.")
            return reviews

    except Exception as e:
        logger.error(f"❌ New Technique Failed: {str(e)}")
        return []
