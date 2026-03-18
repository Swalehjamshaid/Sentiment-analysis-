import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 300, skip: int = 0) -> List[Dict[str, Any]]:
    reviews = []
    # Using the most reliable Google Maps Direct URL format
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            logger.info(f"🚀 Navigating to Place ID: {place_id}")

            # 1. Load Page
            await page.goto(place_url, wait_until="domcontentloaded", timeout=60000)

            # 2. BREAK THE CONSENT WALL (Crucial for Railway/Cloud IPs)
            try:
                # Look for "Accept all" or "Agree" buttons
                consent_btn = page.get_by_role("button", name=re.compile(r"Accept all|Agree|Allow|Accept", re.IGNORECASE)).first
                if await consent_btn.is_visible(timeout=5000):
                    await consent_btn.click()
                    logger.info("✅ Bypassed Google Consent Wall")
                    await page.wait_for_timeout(2000)
            except:
                logger.info("No consent wall detected or already bypassed.")

            # 3. TRIGGER THE REVIEWS PANEL
            try:
                # Target the button that explicitly mentions "Reviews" or the review count
                review_tab = page.locator('button[aria-label*="Reviews"]').first
                await review_tab.click()
                await page.wait_for_timeout(3000)
                logger.info("✅ Reviews panel opened")
            except Exception as e:
                logger.warning(f"Could not find specific Reviews button: {e}. Attempting direct scroll.")

            # 4. TARGETED INTERNAL SCROLLING
            # We target multiple possible scroll containers used by Google
            last_count = 0
            for i in range(30):
                await page.evaluate('''
                    const selectors = [
                        'div[role="main"] div[tabindex="-1"]',
                        '.m67Hec',
                        'div[aria-label*="Reviews"]',
                        'div[role="main"]'
                    ];
                    for (const s of selectors) {
                        const el = document.querySelector(s);
                        if (el && el.scrollHeight > el.clientHeight) {
                            el.scrollTop = el.scrollHeight;
                        }
                    }
                ''')
                
                await page.wait_for_timeout(2000)
                
                # Check for review card elements
                elements = await page.query_selector_all('div.jftiEf')
                current_count = len(elements)
                logger.info(f"🔄 Loop {i+1}: Found {current_count} reviews")
                
                if current_count >= limit:
                    break
                if current_count == last_count and i > 10:
                    break
                last_count = current_count

            # 5. DATA EXTRACTION
            final_elements = await page.query_selector_all('div.jftiEf')
            logger.info(f"🧐 Extracting data from {len(final_elements)} items...")

            for r in final_elements[:limit]:
                try:
                    # Click "More" to expand long text
                    more_btn = await r.query_selector('button:has-text("More")')
                    if more_btn: await more_btn.click()

                    text_el = await r.query_selector('.wiI7pd')
                    author_el = await r.query_selector('.d4r55')
                    rating_el = await r.query_selector('span.kvMYJc')
                    
                    if not text_el and not author_el:
                        continue

                    # Clean extraction
                    text = await text_el.inner_text() if text_el else "No comment"
                    author = await author_el.inner_text() if author_el else "Google User"
                    
                    # Rating extraction from aria-label (e.g., "5 stars")
                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                    rating = int(re.search(r'\d+', rating_raw).group()) if rating_raw else 0

                    reviews.append({
                        "review_id": f"pw_{hash(text + author + str(datetime.now().timestamp()))}",
                        "rating": rating,
                        "text": text,
                        "author_name": author,
                        "google_review_time": datetime.utcnow().isoformat()
                    })
                except Exception:
                    continue
            
            await browser.close()
            logger.info(f"✨ MISSION COMPLETE: Collected {len(reviews)} reviews for Postgres.")

    except Exception as e:
        logger.error(f"❌ Scraper Critical Failure: {str(e)}")
    
    return reviews
