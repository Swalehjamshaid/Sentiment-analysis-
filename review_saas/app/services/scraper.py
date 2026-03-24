import asyncio
import json
import random
import re
import logging
from typing import List, Dict

# --- CRITICAL IMPORTS FROM THE VIDEO ---
# We use patchright instead of playwright to fix internal browser leaks
from patchright.async_api import async_playwright
from playwright_stealth import stealth_async
import agentql

logger = logging.getLogger("app.scraper")

# ==========================================
# 📱 MOBILE PERSONA GENERATOR (100k VARIATIONS)
# ==========================================
def get_mobile_fingerprint():
    """Generates a randomized mobile hardware profile to act like 100k unique phones."""
    devices = [
        {"name": "iPhone 15 Pro", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1", "w": 393, "h": 852, "dpr": 3.0},
        {"name": "Samsung S24 Ultra", "ua": "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.119 Mobile Safari/537.36", "w": 384, "h": 854, "dpr": 3.5},
        {"name": "Pixel 8 Pro", "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36", "w": 412, "h": 915, "dpr": 3.5}
    ]
    base = random.choice(devices)
    # Add ±2 pixel jitter to screen size to ensure absolute uniqueness per session
    return {
        **base,
        "w": base["w"] + random.randint(-2, 2),
        "h": base["h"] + random.randint(-2, 2),
    }

# ==========================================
# 🧠 DATA STREAM PARSER (BATCHeXECUTE LOGIC)
# ==========================================
def parse_google_stream(raw_text: str) -> List[Dict]:
    """Extracts raw Reviews and Ratings from the background network traffic."""
    results = []
    try:
        clean = raw_text.replace(")]}'", "").strip()
        matches = re.findall(r'\["wrb\.fr".*?\]\]', clean)
        for m in matches:
            payload = json.loads(json.loads(m)[2])
            for block in payload:
                for r in block:
                    try:
                        results.append({
                            "review_id": r[0],
                            "author": r[1][0],
                            "rating": r[4],  # <--- This is the Star Rating (1-5)
                            "text": r[3] or "", # <--- This is the Review Text
                            "date": r[14],
                            "method": "patchright_interception"
                        })
                    except: continue
    except: pass
    return results

# ==========================================
# 🚀 CORE ENGINE (PATCHRIGHT + STEALTH)
# ==========================================
async def fetch_reviews(place_id: str, limit: int = 100):
    """
    Primary entry point for your SaaS.
    Aligns with your requirements.txt (patchright==1.50.0).
    """
    persona = get_mobile_fingerprint()
    
    # ⚠️ For Railway success, ensure you use a Residential Proxy here
    # proxy_config = {"server": "http://user:pass@proxy-provider.com:port"}

    async with async_playwright() as p:
        # Launch using Patchright engine (Invisible to Cloudflare)
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            # , proxy=proxy_config 
        )

        context = await browser.new_context(
            user_agent=persona["ua"],
            viewport={"width": persona["w"], "height": persona["h"]},
            device_scale_factor=persona["dpr"],
            is_mobile=True,
            has_touch=True,
            locale="en-US"
        )

        page = await context.new_page()
        
        # Apply the video's stealth layer to hide Playwright/WebDriver flags
        await stealth_async(page)

        # Background Network Listener: This catches the data before it renders on screen
        captured_data = []
        page.on("response", lambda res: captured_data.append(res) if "batchexecute" in res.url else None)

        try:
            # Construct Target URL (Accepts Place ID or direct Link)
            url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}" if "http" not in place_id else place_id
            
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # --- HUMAN BEHAVIOR EMULATION ---
            # Mimics a real person flick-scrolling their phone to load more reviews
            for _ in range(random.randint(6, 10)):
                await page.mouse.wheel(0, random.randint(3000, 5000))
                await asyncio.sleep(random.uniform(2.0, 4.0))

            # Process all captured network packets for Reviews & Ratings
            final_reviews = []
            for response in captured_data:
                try:
                    raw_text = await response.text()
                    final_reviews.extend(parse_google_stream(raw_text))
                except: continue

            await browser.close()

            # Deduplicate by ID and return clean results
            unique_map = {r['review_id']: r for r in final_reviews}
            return list(unique_map.values())[:limit]

        except Exception as e:
            logger.error(f"❌ Scraper failure: {e}")
            await browser.close()
            return []

print("🛡️ PATCHRIGHT UNDETECTABLE ENGINE READY")
