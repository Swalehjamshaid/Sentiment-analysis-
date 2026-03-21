# app/services/scraper.py

import asyncio
from playwright.async_api import async_playwright, Page
from typing import Dict
import logging

logging.basicConfig(level=logging.INFO)


async def scrape_google_reviews(company_name: str) -> Dict:
    """
    Scrapes Google search results for company reviews.
    Returns a dict with rating and number of reviews.
    Uses only Python libraries (Playwright) without Google API.
    """
    logging.info(f"🕵️ Starting scraping for: {company_name}")
    result = {"rating": None, "reviews": None}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page: Page = await context.new_page()

            # Open Google search for reviews
            search_url = f"https://www.google.com/search?q={company_name.replace(' ', '+')}+reviews"
            await page.goto(search_url)

            # Wait for content to load
            await page.wait_for_timeout(3000)

            try:
                # Grab rating element
                rating_el = await page.query_selector('span[aria-label*="stars"]')
                review_count_el = await page.query_selector('span:has-text("reviews")')

                if rating_el:
                    rating_text = await rating_el.get_attribute("aria-label")
                    if rating_text:
                        result["rating"] = float(rating_text.split()[0])

                if review_count_el:
                    reviews_text = await review_count_el.inner_text()
                    if reviews_text:
                        result["reviews"] = int(''.join(filter(str.isdigit, reviews_text)))
            except Exception as e:
                logging.warning(f"⚠️ Could not parse rating/reviews: {e}")

            await browser.close()
    except Exception as e:
        logging.error(f"🛑 Scraper error: {e}")

    logging.info(f"✅ Scraping completed for {company_name}: {result}")
    return result


# Optional test runner
if __name__ == "__main__":
    test_company = "Gloria Jeans Coffees DHA Phase 5"
    data = asyncio.run(scrape_google_reviews(test_company))
    print(data)
