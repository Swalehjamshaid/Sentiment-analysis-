# filename: app/services/scraper.py
import logging
import hashlib
import asyncio
import random
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


def parse_relative_date(date_text: str) -> datetime:
    now = datetime.utcnow()
    date_text = (date_text or "").lower().strip()
    if not date_text:
        return now
    match = re.search(r'(a|an|\d+)\s*(\w+)', date_text)
    if match:
        num_str, unit = match.groups()
        number = 1 if num_str in ('a', 'an') else int(num_str)
        if any(k in unit for k in ['minute', 'min']):
            return now - timedelta(minutes=number)
        if any(k in unit for k in ['hour', 'hr']):
            return now - timedelta(hours=number)
        if 'day' in unit:
            return now - timedelta(days=number)
        if 'week' in unit:
            return now - timedelta(weeks=number)
        if 'month' in unit:
            return now - timedelta(days=number * 30)
        if 'year' in unit:
            return now - timedelta(days=number * 365)
    return now


async def fetch_reviews(
    place_id: str,
    limit: int = 150,
    **kwargs
) -> List[Dict[str, Any]]:
    reviews: List[Dict[str, Any]] = []
    seen = set()
    url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                timezone_id="Asia/Karachi",
                bypass_csp=True,
            )
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = { runtime: {} };
            """)

            page = await context.new_page()
            logger.info(f"Starting reviews scrape for place_id: {place_id}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Consent
            try:
                consent_btn = page.get_by_role("button", name=re.compile(r"(accept all|agree|ok|continue|accept|got it)", re.I))
                if await consent_btn.is_visible(timeout=8000):
                    await consent_btn.click(timeout=10000)
                    await asyncio.sleep(random.uniform(1.2, 2.5))
            except:
                pass

            # ── Tab opening (exactly same as your working version) ──
            tab_found = False
            tab_strategies = [
                page.get_by_role("tab", name=re.compile(r"reviews?|جائزے|تقييمات", re.I)),
                page.get_by_role("tab", name=re.compile(r"\d.*reviews?", re.I)),
                page.locator('[aria-label*="review" i], [aria-label*="جائزہ" i], [aria-label*="تقييم" i]'),
                page.get_by_text(re.compile(r"reviews?|جائزے|تقييمات", re.I)).first,
                page.locator('//div[@role="tablist"]//div[contains(@role,"tab")][contains(translate(text(),"REVIEWS","reviews"),"reviews")]'),
                page.locator('button, div[role="tab"], span[role="tab"] >> text=/reviews?|جائزے/i'),
            ]
            for locator in tab_strategies:
                try:
                    if await locator.count() > 0:
                        first_tab = locator.first
                        if not await first_tab.is_visible():
                            await first_tab.scroll_into_view_if_needed(timeout=5000)
                        await first_tab.click(delay=random.randint(150, 450), timeout=15000, force=True)
                        await asyncio.sleep(random.uniform(2.8, 4.5))
                        await page.wait_for_selector(
                            "div.jftiEf, [data-review-id], .review-dialog-list",
                            state="visible",
                            timeout=25000
                        )
                        tab_found = True
                        logger.info("Reviews panel successfully opened")
                        break
                except Exception as exc:
                    logger.debug(f"Tab strategy failed: {exc}")
                    continue

            if not tab_found:
                logger.warning("All attempts to open Reviews tab failed – possible layout change or block")
                await browser.close()
                return []

            # ── FASTER SCROLL + COLLECTION (same logic, higher speed) ──
            scroll_sels = [
                'div.m6QErb[aria-label*="reviews"]',
                'div[role="main"] div[role="feed"]',
                'div[aria-label*="reviews list"]',
                'div.review-dialog-list',
                'div[role="region"][aria-label*="reviews"]',
            ]
            scroll_container = None
            for sel in scroll_sels:
                container = page.locator(sel).first
                if await container.is_visible(timeout=4000):
                    scroll_container = container
                    logger.debug(f"Using scroll container: {sel}")
                    break

            max_attempts = 60
            no_progress = 0
            prev_count = 0

            for attempt in range(1, max_attempts + 1):
                # Expand "More" faster
                more_btns = page.get_by_role("button", name=re.compile(r"more|مزید", re.I))
                for i in range(min(await more_btns.count(), 20)):
                    try:
                        await more_btns.nth(i).click(timeout=2500, force=True)
                        await asyncio.sleep(0.3)
                    except:
                        pass

                cards = await page.query_selector_all("div.jftiEf, [data-review-id]")

                added = 0
                for card in cards:
                    try:
                        author = (await (await card.query_selector(".d4r55")).inner_text() if await card.query_selector(".d4r55") else "Anonymous").strip()
                        text = (await (await card.query_selector(".wiI7pd")).inner_text() if await card.query_selector(".wiI7pd") else "").strip()
                        rating_text = await (await card.query_selector('[aria-label*="star"]')).get_attribute("aria-label") if await card.query_selector('[aria-label*="star"]') else ""
                        rating = int(re.search(r"\d+", rating_text).group()) if re.search(r"\d+", rating_text) else 0
                        date_str = (await (await card.query_selector(".rsqaWe")).inner_text() if await card.query_selector(".rsqaWe") else "").strip()
                        time_iso = parse_relative_date(date_str).isoformat()

                        key = hashlib.sha256(f"{author}|{text[:120]}|{rating}".encode()).hexdigest()
                        if key in seen:
                            continue

                        reviews.append({
                            "review_id": key,
                            "rating": rating,
                            "text": text,
                            "author_name": author,
                            "google_review_time": time_iso,
                        })
                        seen.add(key)
                        added += 1
                    except:
                        continue

                current = len(reviews)
                logger.info(f"Attempt {attempt}: +{added} → Total {current} reviews")

                if current >= limit:
                    break
                if current == prev_count:
                    no_progress += 1
                    if no_progress >= 12:
                        logger.info("No more new reviews loading → stopping")
                        break
                else:
                    no_progress = 0
                prev_count = current

                # FAST targeted scroll
                if scroll_container:
                    await scroll_container.evaluate("el => el.scrollTop = el.scrollHeight")
                else:
                    await page.evaluate("window.scrollBy(0, 3500)")

                await asyncio.sleep(random.uniform(2.5, 5.5))  # ← SPEED OPTIMIZED

            logger.info(f"✅ Finished scrape – {len(reviews)} reviews ready for Postgres ingest")
            await browser.close()
            return reviews[:limit]

    except Exception as e:
        logger.error(f"Scraper error: {e}", exc_info=True)
        return []
