import asyncio
import re
import logging
from typing import List, Dict, Any

from playwright.async_api import async_playwright, Page
from playwright_stealth import stealth_async

logger = logging.getLogger("app.scraper")


async def fetch_reviews(place_id: str, limit: int = 300) -> List[Dict[str, Any]]:
    """
    Improved Google Maps Reviews Scraper - March 2026 Version
    Using your Scrape.do token
    """
    logger.info(f"🚀 Initializing Video-Logic Scraper for: {place_id} | Limit: {limit}")

    reviews_data: List[Dict[str, Any]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        )
        page: Page = await context.new_page()

        try:
            # Apply stealth
            await stealth_async(page)

            # Load via Scrape.do with your actual token
            scrape_do_url = f"http://api.scrape.do?token=a8d5fe160ee4446c96c85973df0f3ec0798124bd215&url=https://www.google.com/maps/place/?q=place_id:{place_id}&render=true"
            
            logger.info("📡 Loading page via Scrape.do render=true...")
            await page.goto(scrape_do_url, timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=30000)

            # ====================== CLICK REVIEWS TAB ======================
            logger.info("🖱️ Detecting and clicking Reviews tab...")

            tab_selectors = [
                'button[aria-label*="Reviews"]',           # Most reliable in 2026
                'button[role="tab"]:has-text("Reviews")',
                'div[role="tab"]:has-text("Reviews")',
                'button >> text=/Reviews/i',
                '[data-value="Reviews"]',
            ]

            tab_clicked = False
            for selector in tab_selectors:
                try:
                    tab = page.locator(selector).first
                    if await tab.is_visible(timeout=5000):
                        await tab.scroll_into_view_if_needed()
                        await tab.click(timeout=8000)
                        await asyncio.sleep(3.5)
                        logger.info(f"✅ Successfully clicked Reviews tab using: {selector}")
                        tab_clicked = True
                        break
                except Exception:
                    continue

            if not tab_clicked:
                logger.warning("⚠️ Could not click Reviews tab with primary selectors. Trying last resort...")
                try:
                    await page.get_by_role("tab").filter(has_text=re.compile("Reviews", re.I)).first.click(timeout=10000)
                    await asyncio.sleep(4)
                except Exception:
                    logger.warning("⚠️ All tab click attempts failed.")

            # Wait for reviews section
            await asyncio.sleep(3)

            # ====================== SMART SCROLLING ======================
            logger.info("🔄 Smart scrolling to load reviews...")

            last_count = 0
            no_progress = 0
            max_attempts = 35

            for attempt in range(max_attempts):
                await page.evaluate("window.scrollBy(0, 1500)")
                await asyncio.sleep(2.2)

                if attempt % 5 == 0:
                    await page.mouse.wheel(0, 800)

                current_count = await page.locator('div[data-review-id], .jftiEf, .MyEned, article').count()

                if current_count > last_count:
                    logger.info(f"   📈 Loaded {current_count} reviews so far...")
                    last_count = current_count
                    no_progress = 0
                else:
                    no_progress += 1

                if current_count >= limit:
                    logger.info(f"✅ Reached target of {limit} reviews")
                    break

                if no_progress >= 6:
                    logger.warning("⏹️ No new reviews loading. Stopping scroll.")
                    break

            # ====================== EXTRACT REVIEWS ======================
            logger.info("🔍 Extracting review data...")
            review_elements = await page.locator('div[data-review-id], .jftiEf, .MyEned').all()

            for element in review_elements[:limit]:
                try:
                    name = await element.locator('.d4r55, .fontHeadlineSmall').inner_text(timeout=3000).catch(lambda: "Anonymous")
                    rating_text = await element.locator('.kvMYJc').get_attribute('aria-label', timeout=3000).catch(lambda: "0")
                    text = await element.locator('.wiI7pd').inner_text(timeout=5000).catch(lambda: "")

                    rating_match = re.search(r'(\d+\.?\d*)', rating_text or "")
                    rating = float(rating_match.group(1)) if rating_match else 0.0

                    if text.strip():
                        reviews_data.append({
                            "author": name.strip(),
                            "rating": rating,
                            "text": text.strip(),
                            "place_id": place_id,
                        })
                except Exception:
                    continue

            logger.info(f"🏁 Scraping finished. Total reviews extracted: {len(reviews_data)}")

        except Exception as e:
            logger.error(f"❌ Scraper error for {place_id}: {str(e)}", exc_info=True)
        finally:
            await context.close()
            await browser.close()

    return reviews_data
