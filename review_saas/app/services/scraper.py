# filename: app/services/scraper.py
import asyncio
import logging
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# --- ADVANCED CONFIGURATION ---
# Using the ScrapeOps Residential Proxy from your earlier setup
PROXY_URL = "http://scrapeops:d3879aef-d2a6-4422-9b6d-34ff899a638b@residential-proxy.scrapeops.io:8181"

async def fetch_reviews(
    company_id: int, 
    session: AsyncSession, 
    target_url: str = "https://www.amazon.com/dp/B08N5WRWNW", # Default example
    limit: int = 10,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    PLAYWRIGHT MISSION-CRITICAL SCRAPER (2026):
    Automates a real Chromium browser to bypass high-security 
    e-commerce protections (Amazon, eBay, etc.).
    """
    
    all_data = []
    
    async with async_playwright() as p:
        # 1. Launch a Stealth Browser
        # We use a proxy and 'headless=True' for Railway performance
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": PROXY_URL}
        )
        
        # 2. Emulate a Real Device
        # This prevents the 'Bot Detected' page
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        
        page = await context.new_page()
        
        try:
            logger.info(f"🚀 Playwright Navigating to: {target_url}")
            
            # Go to page and wait for 'networkidle' (standard for 2026)
            await page.goto(target_url, wait_until="networkidle", timeout=60000)
            
            # 3. EXTRACTION LOGIC (Example: Amazon Reviews)
            # We use page.locator() which is the modern 2026 standard
            review_elements = page.locator("[data-hook='review']")
            
            count = await review_elements.count()
            logger.info(f"📍 Found {count} data blocks on page.")

            for i in range(min(count, limit)):
                element = review_elements.nth(i)
                
                # Fetching details using relative locators
                author = await element.locator(".a-profile-name").inner_text()
                rating_raw = await element.locator(".a-icon-alt").inner_text()
                body = await element.locator(".review-text-content").inner_text()
                
                all_data.append({
                    "review_id": f"EXT-{i}",
                    "author_name": author.strip() if author else "User",
                    "rating": int(rating_raw[0]) if rating_raw else 5,
                    "text": body.strip() if body else "No text found."
                })

        except Exception as e:
            logger.error(f"❌ Playwright Extraction Failed: {e}")
        
        finally:
            await browser.close()

    logger.info(f"✅ Extracted {len(all_data)} items from {target_url}")
    return all_data
