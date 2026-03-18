import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 300, skip: int = 0) -> List[Dict[str, Any]]:
    reviews = []
    # Use the more standard Maps URL which is less likely to trigger bot detection
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            
            # FORCE English locale. If Google sees a different language, 
            # aria-labels like "Reviews" will be "Rezensionen" or "Reseñas".
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="en-US"
            )
            
            page = await context.new_page()
            logger.info(f"🚀 Navigating to Place ID: {place_id}")

            # 1. Load Page with a longer timeout
            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # 2. BREAK THE CONSENT WALL (More aggressive)
            try:
                # Some regions have a mandatory "Accept all" button
                consent_selectors = ["Accept all", "Agree", "Allow", "Accept"]
                for btn_text in consent_selectors:
                    btn = page.get_by_role("button", name=re.compile(btn_text, re.IGNORECASE)).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        logger.info(f"✅ Bypassed Consent with: {btn_text}")
                        await page.wait_for_timeout(2000)
                        break
            except Exception:
                logger.info("Consent wall not found; proceeding.")

            # 3. TRIGGER THE REVIEWS PANEL (Multiple Fallbacks)
            review_triggered = False
            # Try specific aria-label, then text, then common class
            review_locators = [
                'button[aria-label*="Reviews"]',
                'button:has-text("Reviews")',
                'div[role="tab"]:has-text("Reviews")',
                '.hh7Vgc' # Google's internal class for the review tab
            ]

            for selector in review_locators:
                try:
                    target = page.locator(selector).first
                    if await target.is_visible(timeout=5000):
                        await target.click()
                        review_triggered = True
                        logger.info(f"✅ Reviews panel opened via {selector}")
                        # Wait for the scrollable container to appear
                        await page.wait_for_selector('div.jftiEf', timeout=10000)
                        break
                except Exception:
                    continue

            if not review_triggered:
                logger.warning("Could not find 'Reviews' tab. The page might be in a different layout.")

            # 4. ROBUST INTERNAL SCROLLING
            last_count = 0
            for i in range(30):
                # We inject JS to scroll the specific panel where reviews live
                await page.evaluate('''
                    const scrollable = document.querySelector('div[role="main"] div[tabindex="-1"]') 
                                    || document.querySelector('.m67Hec') 
                                    || document.querySelector('div[aria-label*="Reviews"]');
                    if (scrollable) {
                        scrollable.scrollTop = scrollable.scrollHeight;
                    } else {
                        window.scrollBy(0, 1000);
                    }
                ''')
                
                await page.wait_for_timeout(2000)
                
                elements = await page.query_selector_all('div.jftiEf')
                current_count = len(elements)
                logger.info(f"🔄 Loop {i+1}: Found {current_count} reviews")
                
                if current_count >= limit:
                    break
                # If we've been stuck for 5 loops, exit
                if current_count == last_count and i > 5:
                    break
                last_count = current_count

            # 5. DATA EXTRACTION
            final_elements = await page.query_selector_all('div.jftiEf')
            logger.info(f"🧐 Extracting data from {len(final_elements)} items...")

            for r in final_elements[:limit]:
                try:
                    # Expand long text
                    more_btn = await r.query_selector('button:has-text("More")')
                    if more_btn: 
                        await more_btn.click()
                        await page.wait_for_timeout(200)

                    text_el = await r.query_selector('.wiI7pd')
                    author_el = await r.query_selector('.d4r55')
                    rating_el = await r.query_selector('span.kvMYJc')
                    
                    if not author_el: continue

                    text = await text_el.inner_text() if text_el else ""
                    author = await author_el.inner_text() if author_el else "Google User"
                    
                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                    rating_match = re.search(r'(\d+)', rating_raw)
                    rating = int(rating_match.group(1)) if rating_match else 0

                    reviews.append({
                        "review_id": f"pw_{hash(text + author + str(datetime.now().timestamp()))}",
                        "rating": rating,
                        "text": text,
                        "author_name": author,
                        "google_review_time": datetime.utcnow().isoformat()
                    })
                except Exception as e:
                    logger.debug(f"Row skip: {e}")
                    continue
            
            await browser.close()
            logger.info(f"✨ MISSION COMPLETE: Collected {len(reviews)} reviews.")

    except Exception as e:
        logger.error(f"❌ Scraper Critical Failure: {str(e)}")
    
    return reviews
