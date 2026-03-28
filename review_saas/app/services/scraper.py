import asyncio
from typing import List, Dict, Optional
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================
# SCRAPER FUNCTION
# =============================
async def fetch_reviews(
    place_id: str,
    name: Optional[str] = None,
    limit: int = 300
) -> List[Dict]:
    """
    Scrape Google Reviews for a given place_id.

    Args:
        place_id (str): Google Maps Place ID
        name (Optional[str]): Friendly name for logging
        limit (int): Maximum number of reviews to fetch

    Returns:
        List[Dict]: List of reviews with author, rating, date, text
    """
    reviews: List[Dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        page = await context.new_page()
        await stealth_async(page)  # Make browser undetectable

        try:
            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            await page.goto(url, timeout=60000)

            # Wait for reviews section
            await page.wait_for_selector("button[jsaction*='pane.review']", timeout=15000)

            # Click to open reviews
            review_button = await page.query_selector("button[jsaction*='pane.review']")
            if review_button:
                await review_button.click()
                await asyncio.sleep(2)

            # Scroll reviews
            last_height = 0
            scroll_attempt = 0
            while len(reviews) < limit and scroll_attempt < 20:
                review_elements = await page.query_selector_all("div[class*='ODSEW-ShBeI-content']")
                for elem in review_elements[len(reviews):]:
                    try:
                        author = await elem.query_selector_eval(".d4r55", "el => el.textContent")
                        rating = await elem.query_selector_eval(".kvMYJc", "el => el.getAttribute('aria-label')")
                        date = await elem.query_selector_eval(".rsqaWe", "el => el.textContent")
                        text = await elem.query_selector_eval(".MyEned", "el => el.textContent")
                        reviews.append({
                            "author": author.strip() if author else "",
                            "rating": rating.strip() if rating else "",
                            "date": date.strip() if date else "",
                            "text": text.strip() if text else ""
                        })
                    except Exception:
                        continue

                # Scroll container
                container = await page.query_selector("div[class*='m6QErb']")
                if container:
                    await container.evaluate("(el) => el.scrollBy(0, 1000)")
                    await asyncio.sleep(1)
                    scroll_attempt += 1
                else:
                    break

                # Stop if no new reviews
                new_height = await container.evaluate("(el) => el.scrollHeight") if container else 0
                if new_height == last_height:
                    break
                last_height = new_height

            logger.info(f"Scraped {len(reviews)} reviews for {name or place_id}")

        except Exception as e:
            logger.error(f"Error scraping reviews for {name or place_id}: {e}")
        finally:
            await browser.close()

    return reviews

# =============================
# TESTING SCRIPT
# =============================
if __name__ == "__main__":
    test_place_id = "ChIJN1t_tDeuEmsRUsoyG83frY4"  # Replace with real Place ID
    data = asyncio.run(fetch_reviews(place_id=test_place_id, name="Test Place", limit=50))
    print(f"Fetched {len(data)} reviews")
