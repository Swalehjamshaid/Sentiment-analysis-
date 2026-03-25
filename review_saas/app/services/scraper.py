import asyncio
import re
import random
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger("ReviewSaaS.Scraper")

# Your Smartproxy Pool
PROXIES = [
    "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
    "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
    "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
    "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
    "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
]

async def fetch_reviews(place_id: str, limit: int = 50):
    """
    ASYNCHRONOUS scraper logic to fix the 'Sync API inside asyncio loop' error.
    """
    logger.info(f"🚀 Starting Async Scraper for: {place_id}")
    
    # Select random proxy
    selected_proxy = random.choice(PROXIES)

    # Use async context manager
    async with async_playwright() as p:
        # Must AWAIT launch
        browser = await p.firefox.launch(
            headless=True,
            proxy={"server": selected_proxy}
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
        )
        page = await context.new_page()

        # Navigation (AWAIT everything)
        await page.goto("https://www.google.com/maps", wait_until="networkidle")
        
        try:
            await page.get_by_role("button", name="Accept all").click()
        except:
            pass

        # Search
        await page.locator("#searchboxinput").fill(place_id)
        await page.keyboard.press("Enter")
        
        # Wait for business profile
        await page.wait_for_selector(".hfpxzc")
        await page.locator(".hfpxzc").first.click()

        # Go to Reviews Tab
        await page.wait_for_selector("button[role='tab'][aria-label*='Reviews']")
        await page.get_by_role("button", name=re.compile(r"Reviews", re.IGNORECASE)).click()

        reviews_list = []
        visited_ids = set()

        # Scrolling Loop
        while len(reviews_list) < limit:
            await page.mouse.wheel(0, 3000)
            # CRITICAL: Use asyncio.sleep (not time.sleep) to prevent blocking
            await asyncio.sleep(random.uniform(2, 4)) 

            # Video Logic selectors
            elements = await page.locator(".jfti30").all()
            
            for el in elements:
                if len(reviews_list) >= limit:
                    break
                
                try:
                    name = await el.locator(".d4r55").inner_text()
                    
                    # Rating extraction
                    aria_label = await el.locator(".kvS7h").get_attribute("aria-label")
                    rating = int(re.search(r'\d+', aria_label).group()) if aria_label else 0

                    # Expand 'More'
                    try:
                        more_btn = el.locator("button:has-text('More')")
                        if await more_btn.is_visible():
                            await more_btn.click()
                    except:
                        pass
                    
                    text = await el.locator(".wiI7pd").inner_text()

                    review_id = f"{name}-{text[:20]}"
                    if review_id not in visited_ids:
                        reviews_list.append({
                            "author": name,
                            "rating": rating,
                            "text": text
                        })
                        visited_ids.add(review_id)
                except:
                    continue
            
            logger.info(f"Progress: {len(reviews_list)}/{limit}")

        await browser.close()
        return reviews_list

# Alias to keep routes working
scrape_google_reviews = fetch_reviews
