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
    limit: int = 300,  # increased default limit
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
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # Consent - quick
            try:
                await page.get_by_role("button", name=re.compile(r"(accept all|agree|ok|continue|accept|got it)", re.I)).click(timeout=6000)
                await asyncio.sleep(random.uniform(0.8, 1.8))
            except:
                pass

            # ── FAST & ROBUST Tab opening ──
            tab_found = False
            tab_strategies = [
                page.get_by_role("tab", name=re.compile(r"reviews?|جائزے|جائزہ|تقييمات|تقييم", re.I | re.U)),
                page.get_by_role("tab", name=re.compile(r"\d.*(reviews?|جائزے|تقييمات)", re.I | re.U)),
                page.locator('[aria-label*="review" i], [aria-label*="جائزے" i], [aria-label*="تقييم" i], [aria-label*="Reviews" i]'),
                page.get_by_text(re.compile(r"(reviews?|جائزے|تقييمات|Reviews\s*\d+)", re.I | re.U)).first,
                page.locator('//div[@role="tablist"]//div[@role="tab"][contains(translate(., "REVIEWSجائزےتقييمات", "reviewsجائزےتقييمات"), "reviews") or contains(., "جائزے")]'),
                page.locator('[role="tab"], button, [role="button"] >> text=/reviews?|جائزے|تقييم/i'),
            ]

            for loc in tab_strategies:
                try:
                    if await loc.count():
                        tab = loc.first
                        await tab.scroll_into_view_if_needed(timeout=4000)
                        await tab.hover(timeout=3000)
                        await tab.click(delay=random.randint(80, 250), timeout=10000, force=True)
                        await asyncio.sleep(random.uniform(2.0, 3.5))
                        await page.wait_for_selector(
                            "div.jftiEf, [data-review-id], [role='listitem']",
                            timeout=18000
                        )
                        tab_found = True
                        logger.info("Reviews panel opened")
                        break
                except:
                    continue

            if not tab_found:
                logger.warning("Reviews tab failed to open")
                await browser.close()
                return []

            # ── SUPER FAST SCROLL & COLLECTION ──
            scroll_selectors = [
                'div.m6QErb[aria-label*="reviews"]',
                'div[role="feed"]',
                'div[aria-label*="reviews list"]',
                'div.review-dialog-list',
                'div[role="main"] > div > div[aria-label*="reviews"]',
            ]
            scroll_container = None
            for sel in scroll_selectors:
                try:
                    cont = page.locator(sel).first
                    if await cont.is_visible(timeout=3000):
                        scroll_container = cont
                        break
                except:
                    pass

            max_attempts = 80
            no_progress = 0
            prev = 0

            for att in range(1, max_attempts + 1):
                # Expand More quickly
                more = page.get_by_role("button", name=re.compile(r"more|مزید|See more", re.I))
                cnt = await more.count()
                for i in range(min(cnt, 25)):
                    try:
                        await more.nth(i).click(timeout=2000, force=True)
                        await asyncio.sleep(0.25)
                    except:
                        pass

                cards = await page.query_selector_all("div.jftiEf, [data-review-id], [role='listitem']")

                added = 0
                for card in cards:
                    try:
                        author_el = await card.query_selector(".d4r55, .TSUbDb")
                        author = (await author_el.inner_text() if author_el else "Anonymous").strip()

                        text_el = await card.query_selector(".wiI7pd, .MyEned")
                        text = (await text_el.inner_text() if text_el else "").strip()

                        stars = await card.query_selector('[aria-label*="star rating"]')
                        rating_str = await stars.get_attribute("aria-label") if stars else ""
                        rating = int(re.search(r'\d+', rating_str).group()) if re.search(r'\d+', rating_str) else 0

                        date_el = await card.query_selector(".rsqaWe, .DU9Pgb")
                        date_str = (await date_el.inner_text() if date_el else "").strip()
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

                curr = len(reviews)
                logger.info(f"Attempt {att}: +{added} → {curr} total")

                if curr >= limit:
                    break

                if curr == prev:
                    no_progress += 1
                    if no_progress >= 15:
                        logger.info("No more loading → stop")
                        break
                else:
                    no_progress = 0
                prev = curr

                # Fast targeted scroll
                if scroll_container:
                    await scroll_container.evaluate("el => el.scrollTop += 4000 || el.scrollBy(0, 4000)")
                else:
                    await page.evaluate("window.scrollBy(0, 4000)")

                await asyncio.sleep(random.uniform(2.0, 4.2))  # fast but safe

            logger.info(f"Finished - {len(reviews)} reviews fetched (ready for Postgres ingest)")
            await browser.close()
            return reviews[:limit]

    except Exception as e:
        logger.error(f"Scraper failed: {e}", exc_info=True)
        return []
