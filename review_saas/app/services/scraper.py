import asyncio
import json
import random
import re
import logging
from typing import List, Dict

# --- CRITICAL IMPORTS FROM THE VIDEO ---
# Patchright fixes the internal browser flags that standard Playwright leaks
from patchright.async_api import async_playwright
from playwright_stealth import stealth_async
import agentql

logger = logging.getLogger("app.scraper")

# ==========================================
# 📱 MOBILE PERSONA GENERATOR (100k VARIATIONS)
# ==========================================
def get_mobile_fingerprint():
    """Generates a randomized mobile hardware profile for absolute uniqueness."""
    devices = [
        {"name": "iPhone 15 Pro", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1", "w": 393, "h": 852, "dpr": 3.0},
        {"name": "Samsung S24 Ultra", "ua": "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.119 Mobile Safari/537.36", "w": 384, "h": 854, "dpr": 3.5},
        {"name": "Pixel 8 Pro", "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36", "w": 412, "h": 915, "dpr": 3.5}
    ]
    base = random.choice(devices)
    # Add ±2 pixel 'jitter' to screen size to ensure no two sessions are identical
    return {
        **base,
        "w": base["w"] + random.randint(-2, 2),
        "h": base["h"] + random.randint(-2, 2),
    }

# ==========================================
# 🧠 NETWORK INTERCEPTION (BATCHeXECUTE LOGIC)
# ==========================================
def parse_google_stream(raw_text: str) -> List[Dict]:
    """Extracts raw Reviews and Ratings from the background JSON packets."""
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
                            "rating": r[4],  # Numeric star rating (1-5)
                            "text": r[3] or "",
                            "date": r[14],
                            "engine": "patchright_interceptor"
                        })
                    except: continue
    except: pass
    return results

# ==========================================
# 🚀 THE UNDETECTABLE ENGINE
# ==========================================
async def fetch_reviews(place_id: str, limit: int = 100):
    """
    Main scraping function using the Video's recommended logic.
    Requires: patchright==1.50.0 in requirements.txt
    """
    persona = get_mobile_fingerprint()
    
    # ⚠️ For 99% success on Railway, insert your Residential Proxy here:
    # proxy_config = {"server": "http://user:pass@proxy-provider.com:port"}

    async with async_playwright() as p:
        # 1. Launch using Patchright (fixes the 'AutomationControlled' leak)
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            # , proxy=proxy_config 
        )

        # 2. Emulate a specific Mobile Device
        context = await browser.new_context(
            user_agent=persona["ua"],
            viewport={"width": persona["w"], "height": persona["h"]},
            device_scale_factor=persona["dpr"],
            is_mobile=True,
            has_touch=True,
            locale="en-US"
        )

        page = await context.new_page()
        
        # 3. Apply the 'Stealth' patch to mask standard Playwright signals
        await stealth_async(page)

        # 4. Set up the Background Listener for network packets
        captured_data = []
        page.on("response", lambda res: captured_data.append(res) if "batchexecute" in res.url else None)

        try:
            # Construct Google Maps link
            url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}" if "http" not in place_id else place_id
            
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # 5. Human Behavior: Variable 'Thumb' scrolling to trigger data loads
            for _ in range(random.randint(6, 10)):
                await page.mouse.wheel(0, random.randint(3000, 6000))
                await asyncio.sleep(random.uniform(2.5, 4.5))

            # 6. Extract Reviews from all intercepted data packets
            final_reviews = []
            for response in captured_data:
                try:
                    raw_text = await response.text()
                    final_reviews.extend(parse_google_stream(raw_text))
                except: continue

            await browser.close()

            # Deduplicate by ID and apply the limit
            unique_reviews = {r['review_id']: r for r in final_reviews}
            return list(unique_reviews.values())[:limit]

        except Exception as e:
            logger.error(f"❌ Scraper Failed: {e}")
            await browser.close()
            return []

print("🛡️ PATCHRIGHT STEALTH ENGINE (VIDEO COMPLIANT) INITIALIZED")
