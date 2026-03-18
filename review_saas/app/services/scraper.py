import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 300, skip: int = 0) -> List[Dict[str, Any]]:
    """
    Fetches Google Maps reviews using Playwright.
    :param place_id: The Google Place ID to scrape.
    :param limit: Maximum number of reviews to collect.
    :param skip: Number of reviews to skip (pagination placeholder).
    """
    reviews = []
    # Standard Google Maps place URL
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            # Launch browser with required arguments for Cloud environments (Railway/Render)
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            
            # CRITICAL: Force English locale and a modern User Agent
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="en-US"
            )
            
            page = await context.new_page()
            logger.info(f"🚀 Starting Scraper for Place ID: {place_id}")

            # 1. Navigation
            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # 2. Bypass Google Cookie Consent (Handles EU/US variants)
            try:
                consent_patterns = r"Accept all|Agree|Allow|Accept"
                consent_btn = page.get_by_role("button", name=re.compile(consent_patterns, re.IGNORECASE)).first
                if await consent_btn.is_visible(timeout=5000):
                    await consent_btn.click()
                    logger.info("✅ Google Consent Wall Bypassed")
                    await page.wait_for_timeout(2000)
            except Exception:
                logger.info("No consent wall detected.")

            # 3. Open Reviews Panel
            # We look for the button that explicitly says 'Reviews'
            review_tab_triggered = False
            selectors = [
                'button[aria-label*="Reviews"]',
                'button:has-text("Reviews")',
                'div[role="tab"]:has-text("Reviews")',
                '.hh7Vgc' # Obfuscated class fallback
            ]

            for selector in selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=5000):
                        await btn.click()
                        review_tab_triggered = True
                        logger.info(f"✅ Reviews tab opened via {selector}")
                        # Wait for the first review card to appear in the DOM
                        await page.wait_for_selector('div.jftiEf', timeout=10000)
                        break
                except Exception:
                    continue

            if not review_tab_triggered:
                logger.warning("⚠️ Could not find 'Reviews' button. Attempting to scroll the main container.")

            # 4. Infinite Scroll Logic
            last_count = 0
            # Limit the loops to prevent infinite hanging if no reviews are found
            for i in range(40):
                # Target the specific scrollable containers Google uses
                await page.evaluate('''
                    const scroller = document.querySelector('div[role="main"] div[tabindex="-1"]') 
                                   || document.querySelector('.m67Hec')
                                   || document.querySelector('div[aria-label*="Reviews"]');
                    if (scroller) {
                        scroller.scrollTop = scroller.scrollHeight;
                    }
                ''')
                
                await page.wait_for_timeout(2000) # Wait for network/rendering
                
                # 'div.jftiEf' is the unique class for individual review cards
                elements = await page.query_selector_all('div.jftiEf')
                current_count = len(elements)
                logger.info(f"🔄 Scrolling: Loop {i+1} | Found {current_count} reviews")
                
                if current_count >= limit:
                    break
                # If the count doesn't increase for 5 consecutive loops, stop
                if current_count == last_count and i > 5:
                    break
                last_count = current_count

            # 5. Extraction Phase
            all_review_cards = await page.query_selector_all('div.jftiEf')
            logger.info(f"🧐 Extracting data from {len(all_review_cards)} cards...")

            for card in all_review_cards[:limit]:
                try:
                    # Expand long reviews
                    more_btn = await card.query_selector('button:has-text("More")')
                    if more_btn: 
                        await more_btn.click()
                        await page.wait_for_timeout(200)

                    # Extract text, author, and rating
                    text_el = await card.query_selector('.wiI7pd')
                    author_el = await card.query_selector('.d4r55')
                    rating_el = await card.query_selector('span.kvMYJc')
                    
                    if not author_el: continue

                    text = await text_el.inner_text() if text_el else ""
                    author = await author_el.inner_text() if author_el else "Google User"
                    
                    # Get rating from aria-label (e.g., '5 stars')
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
                    logger.debug(f"Row skip error: {e}")
                    continue
            
            await browser.close()
            logger.info(f"✨ MISSION COMPLETE: Collected {len(reviews)} reviews.")

    except Exception as e:
        logger.error(f"❌ Scraper CRITICAL FAILURE: {str(e)}")
    
    return reviews
