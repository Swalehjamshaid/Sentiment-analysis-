import logging
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

def parse_relative_date(date_text: str) -> datetime:
    """Approximates a datetime from Google's relative strings."""
    now = datetime.utcnow()
    date_text = date_text.lower()
    
    number = 1
    parts = date_text.split()
    for part in parts:
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
    limit: int = 300,
    skip: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    
    reviews: List[Dict[str, Any]] = []
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    # Correct URL format for Google Maps Place IDs
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()

            logger.info(f"🚀 Opening Google Maps for Place ID: {place_id}")
            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # Ensure we are on the reviews tab/view
            try:
                await page.wait_for_selector('div.m67qec', timeout=10000) # Reviews tab selector
                await page.click('div.m67qec')
                await page.wait_for_timeout(2000)
            except:
                logger.warning("⚠️ Direct reviews tab not found, attempting to find button...")

            collected_ids = set()
            scroll_attempts = 0
            MAX_SCROLL = 60 

            while len(reviews) < limit and scroll_attempts < MAX_SCROLL:
                # Expand long reviews
                more_buttons = await page.query_selector_all('button[aria-label*="See more"]')
                for btn in more_buttons:
                    try: await btn.click(timeout=500)
                    except: pass

                elements = await page.query_selector_all('div.jftiEf')

                for r in elements:
                    try:
                        text_el = await r.query_selector('.wiI7pd')
                        rating_el = await r.query_selector('span.kvMYJc')
                        author_el = await r.query_selector('.d4r55')
                        date_el = await r.query_selector('.rsqaWe')

                        text = await text_el.inner_text() if text_el else ""
                        author = await author_el.inner_text() if author_el else "Anonymous"
                        date_text = await date_el.inner_text() if date_el else ""
                        
                        # Permanent ID based on text and author
                        review_id = hashlib.md5(f"{text}{author}".encode()).hexdigest()

                        if review_id in collected_ids:
                            continue

                        rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                        try:
                            rating = int(rating_raw.split()[0])
                        except:
                            rating = 0

                        review_time = parse_relative_date(date_text)

                        # Date filtering
                        if start_dt and review_time < start_dt: continue
                        if end_dt and review_time > end_dt: continue

                        if text:
                            reviews.append({
                                "review_id": review_id,
                                "rating": rating,
                                "text": text,
                                "author_name": author,
                                "google_review_time": review_time.isoformat()
                            })
                            collected_ids.add(review_id)

                        if len(reviews) >= limit: break

                    except Exception as e:
                        continue

                # Scroll the review list container
                await page.mouse.wheel(0, 4000)
                await page.wait_for_timeout(2000)
                scroll_attempts += 1

            await browser.close()
            logger.info(f"✅ Success! Fetched {len(reviews)} reviews.")

    except Exception as e:
        logger.error(f"❌ Scraper failure: {e}")

    return reviews
