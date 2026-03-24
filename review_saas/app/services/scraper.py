import asyncio
import random
import json
from typing import Dict, List
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# 📱 2026 High-End Mobile User Agents
# Matching these to your 4G/5G Proxy is critical for "Trust Score"
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro Build/UQ1A.240205.004) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.64 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
]

def clean(text: str) -> str:
    return " ".join(text.split()) if text else ""

def parse_reviews(raw: str) -> List[Dict]:
    reviews = []
    try:
        if raw.startswith(")]}'"):
            raw = raw[4:]
        data = json.loads(raw)
        if len(data) < 3 or not data[2]:
            return []
        for r in data[2]:
            try:
                reviews.append({
                    "review_id": r[0],
                    "author": r[1][0] if r[1] else "Anonymous",
                    "rating": r[4],
                    "text": clean(r[3]),
                    "relative_time": r[14],
                    "total_author_reviews": r[12][1][1] if r[12] and r[12][1] else 0
                })
            except:
                continue
    except:
        pass
    return reviews

async def fetch_reviews(place_id: str, limit: int = 500):
    collected = {}
    
    # ⚡ EXTREMELY POWERFUL PROXY CONFIG
    # Use 4G/5G Residential Proxies from providers like Bright Data or Oxylabs
    PROXY_SETTINGS = {
        "server": "http://your-mobile-proxy-endpoint.com:port",
        "username": "your_username",
        "password": "your_password"
    }

    async with async_playwright() as p:
        # Launch with proxy and slow_mo to mimic human interaction
        browser = await p.chromium.launch(
            headless=True, 
            proxy=PROXY_SETTINGS,
            args=["--disable-blink-features=AutomationControlled"]
        )

        # Emulate a specific high-end mobile device
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': 390, 'height': 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
            locale="en-US",
            timezone_id="America/New_York" # Match this to your proxy location!
        )

        page = await context.new_page()
        
        # Apply Stealth to bypass 'navigator.webdriver' checks
        await stealth_async(page)

        # Capture background API traffic
        async def handle_response(response):
            if "listentitiesreviews" in response.url:
                try:
                    raw = await response.text()
                    parsed = parse_reviews(raw)
                    for r in parsed:
                        collected[r["review_id"]] = r
                except:
                    pass

        page.on("response", handle_response)

        # 🌍 Navigate to Google Maps (Mobile Interface)
        # 2026 URL structure for higher stability
        url = f"https://www.google.com/maps/search/?api=1&query_place_id={place_id}"
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Random wait to simulate human "looking" at the screen
            await asyncio.sleep(random.uniform(2, 4))

            # Click the 'Reviews' tab - Logic adapted for 2026 Mobile UI
            review_btn = page.get_by_role("button", name="Reviews")
            if await review_btn.is_visible():
                await review_btn.click()
            else:
                # Fallback: Click the rating stars
                await page.click('span[role="img"][aria-label*="stars"]')

            await asyncio.sleep(2)

            # 🔥 HUMAN-LIKE SCROLLING ENGINE
            print(f"✅ Connection Secure. Starting extraction for {place_id}...")
            
            last_count = 0
            for _ in range(50): # Scroll iterations
                if len(collected) >= limit:
                    break
                
                # Scroll in small, varying "thumb" increments
                scroll_amount = random.randint(700, 1500)
                await page.mouse.wheel(0, scroll_amount)
                
                # Important: Move mouse slightly to simulate activity
                await page.mouse.move(random.randint(0, 100), random.randint(0, 100))
                
                # Wait for data to load - 4G/5G speeds vary
                await asyncio.sleep(random.uniform(1.2, 2.8))
                
                if len(collected) == last_count:
                    # If stuck, try a larger "swipe"
                    await page.mouse.wheel(0, 3000)
                    await asyncio.sleep(3)
                
                last_count = len(collected)
                print(f"📦 Progress: {len(collected)} reviews found...")

        except Exception as e:
            print(f"⚠️ Critical Error: {e}")
        finally:
            await browser.close()

    return list(collected.values())[:limit]

if __name__ == "__main__":
    # Test with a popular location
    PLACE_ID = "ChIJ8S6kk9YJGTkRWK6XHzCKSrA"
    results = asyncio.run(fetch_reviews(PLACE_ID, limit=100))
    
    # Save for ReviewSaaS Sentiment Analysis
    with open("master_reviews.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    
    print(f"🔥 Success! Captured {len(results)} reviews.")
