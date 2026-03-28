# filename: test_amazon_price.py
import asyncio
import logging
from playwright.async_api import async_playwright

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("amazon_test")

# --- CONFIGURATION ---
# Using your ScrapeOps Residential Proxy to bypass Amazon's regional blocks
PROXY_URL = "http://scrapeops:d3879aef-d2a6-4422-9b6d-34ff899a638b@residential-proxy.scrapeops.io:8181"

# The Amazon Product URL you want to test
TEST_URL = "https://www.amazon.com/dp/B08N5WRWNW" # Example: Apple MacBook Air

async def fetch_amazon_price():
    """
    STEALTH PRICE FETCH:
    Automates a Chromium browser to pull live pricing data.
    """
    async with async_playwright() as p:
        logger.info("🎬 Launching Stealth Browser...")
        
        # 1. Launch Browser with your Residential Proxy
        browser = await p.chromium.launch(
            headless=True, 
            proxy={"server": PROXY_URL}
        )
        
        # 2. Set Context with a Real User Agent
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        
        try:
            logger.info(f"🛰️ Navigating to: {TEST_URL}")
            
            # Navigate and wait for the page to load 2026-style
            await page.goto(TEST_URL, wait_until="domcontentloaded", timeout=60000)
            
            # 3. EXTRACTION (Using Amazon's 2026 Selector patterns)
            # Fetch Product Title
            title_element = await page.query_selector("#productTitle")
            title = await title_element.inner_text() if title_element else "Title Not Found"

            # Fetch Price (Handles the 'Whole' and 'Fraction' parts)
            price_whole = await page.query_selector(".a-price-whole")
            price_fraction = await page.query_selector(".a-price-fraction")
            
            if price_whole:
                whole = await price_whole.inner_text()
                fraction = await price_fraction.inner_text() if price_fraction else "00"
                full_price = f"${whole.strip()}{fraction.strip()}"
            else:
                full_price = "Price Currently Unavailable"

            # --- OUTPUT RESULTS ---
            print("\n" + "="*30)
            print(f"📦 PRODUCT: {title.strip()[:50]}...")
            print(f"💰 PRICE  : {full_price}")
            print("="*30 + "\n")

        except Exception as e:
            logger.error(f"❌ Extraction Failed: {e}")
            # If blocked, Amazon usually shows a 'Captcha' page
            if "captcha" in await page.content():
                logger.error("🛑 BLOCKED: Amazon is showing a CAPTCHA. Check Proxy Rotation.")
        
        finally:
            await browser.close()
            logger.info("🔌 Browser Closed.")

if __name__ == "__main__":
    asyncio.run(fetch_amazon_price())
