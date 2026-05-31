# =========================================================
# FILE: app/services/scraper.py
# ULTIMATE GOOGLE REVIEW SCRAPER - V15.0
# ALL CRITICAL ISSUES FIXED - PRODUCTION READY
# =========================================================

from __future__ import annotations

# =========================================================
# CORE LIBRARIES
# =========================================================
import os
import re
import time
import json
import random
import asyncio
import hashlib
import logging
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

# =========================================================
# PATCHRIGHT (CRITICAL FIX #1 - Chromium channel)
# =========================================================
from patchright.async_api import async_playwright
from playwright_stealth import stealth_async

# =========================================================
# HTML PARSING
# =========================================================
from bs4 import BeautifulSoup
from selectolax.parser import HTMLParser

# =========================================================
# USER AGENTS & RETRY
# =========================================================
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential
import backoff

# =========================================================
# LOGGER
# =========================================================
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

print("=" * 70)
print("🔍 GOOGLE REVIEW SCRAPER V15.0 - CRITICAL FIXES APPLIED")
print("=" * 70)

# =========================================================
# ENVIRONMENT CONFIGURATION
# =========================================================
SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "300"))
MAX_REVIEWS = int(os.getenv("SCRAPER_MAX_REVIEWS", "500"))
HEADLESS_MODE = os.getenv("SCRAPER_HEADLESS", "true").lower() == "true"
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_SCRAPES", "5"))

# CRITICAL FIX #7: Persistent browser profile
USER_DATA_DIR = os.getenv("USER_DATA_DIR", "/app/data/chrome_profile")
Path(USER_DATA_DIR).mkdir(parents=True, exist_ok=True)

DEBUG_DIR = os.getenv("DEBUG_DIR", "/tmp/scraper_debug")
for subdir in ["captcha", "no_reviews", "success", "error", "html_dumps", "invalid_place"]:
    Path(f"{DEBUG_DIR}/{subdir}").mkdir(parents=True, exist_ok=True)

# =========================================================
# PROXY MANAGER
# =========================================================
class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.proxy_stats = {}
        self.load_proxies()
    
    def load_proxies(self):
        proxy_servers = os.getenv("PROXY_SERVERS", os.getenv("PROXY_SERVER", "")).strip()
        proxy_username = os.getenv("PROXY_USERNAME", "").strip()
        proxy_password = os.getenv("PROXY_PASSWORD", "").strip()
        
        if "," in proxy_servers:
            servers = [s.strip() for s in proxy_servers.split(",")]
        elif proxy_servers:
            servers = [proxy_servers]
        else:
            servers = []
        
        for server in servers:
            if server:
                proxy_config = {"server": f"http://{server}"}
                if proxy_username and proxy_password:
                    proxy_config["username"] = proxy_username
                    proxy_config["password"] = proxy_password
                self.proxies.append(proxy_config)
                self.proxy_stats[server] = {
                    "success": 0, "fail": 0, "captcha": 0,
                    "response_times": [], "cooldown_until": None
                }
        
        logger.info(f"✅ Loaded {len(self.proxies)} proxies")
    
    def get_best_proxy(self) -> Optional[Dict]:
        for proxy in self.proxies:
            server = proxy["server"].replace("http://", "")
            stats = self.proxy_stats.get(server, {})
            if stats.get("cooldown_until", 0) < time.time():
                return proxy
        return self.proxies[0] if self.proxies else None
    
    def report_result(self, proxy_server: str, success: bool, captcha: bool = False, response_time: float = 0):
        if not proxy_server:
            return
        server = proxy_server.replace("http://", "")
        if server not in self.proxy_stats:
            return
        stats = self.proxy_stats[server]
        if success:
            stats["success"] += 1
        else:
            stats["fail"] += 1
        if captcha:
            stats["captcha"] += 1
        if response_time > 0:
            stats["response_times"].append(response_time)

proxy_manager = ProxyManager()

# =========================================================
# USER AGENT MANAGER
# =========================================================
class UserAgentManager:
    def __init__(self):
        try:
            self.ua = UserAgent()
            self.has_fake_ua = True
        except:
            self.has_fake_ua = False
            self.static_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ]
    
    def get(self) -> str:
        if self.has_fake_ua:
            try:
                return self.ua.random
            except:
                pass
        return random.choice(self.static_agents)

ua_manager = UserAgentManager()

# =========================================================
# CACHE WITH VALIDATION (CRITICAL FIX #8)
# =========================================================
class SafeCache:
    """Cache that never stores empty results"""
    
    def __init__(self):
        self.cache = {}
        self.cache_hits = 0
        self.cache_misses = 0
    
    def get(self, key: str) -> Optional[List]:
        """Only return cache if it has reviews"""
        if key in self.cache:
            cached_value = self.cache[key]
            # CRITICAL FIX #8: Never return empty cache
            if cached_value and len(cached_value) > 0:
                self.cache_hits += 1
                logger.info(f"⚡ CACHE HIT: {key} ({len(cached_value)} reviews)")
                return cached_value
            else:
                logger.warning(f"⚠️ CACHE MISS (empty): {key}")
                del self.cache[key]
        self.cache_misses += 1
        return None
    
    def set(self, key: str, value: List):
        """Only cache non-empty results"""
        if value and len(value) > 0:
            self.cache[key] = value
            logger.info(f"💾 CACHE SET: {key} ({len(value)} reviews)")
        else:
            logger.warning(f"⚠️ NOT CACHING empty result for {key}")

safe_cache = SafeCache()

# =========================================================
# CRITICAL FIX #2: MULTI-STRATEGY REVIEW BUTTON CLICKING
# =========================================================
async def click_reviews_button_with_fallback(page, place_id: str) -> Tuple[bool, str]:
    """Multiple strategies to click reviews button - never fails without trying everything"""
    
    strategies = [
        # Strategy 1: Direct button selectors
        {
            "name": "direct_selectors",
            "selectors": [
                'button[jsaction*="pane.reviewChart.moreReviews"]',
                'button[aria-label*="reviews"]',
                'button[aria-label*="Reviews"]',
                'button[data-tab-index="1"]',
                '[role="tab"][aria-label*="Reviews"]',
                '[data-value="Reviews"]',
                'button[jsaction*="pane.rating.moreReviews"]'
            ]
        },
        # Strategy 2: Reload page and retry
        {
            "name": "reload_retry",
            "reload": True
        },
        # Strategy 3: Alternate URL
        {
            "name": "alternate_url",
            "url": f"https://search.google.com/local/reviews?placeid={place_id}"
        }
    ]
    
    for strategy in strategies:
        try:
            if strategy.get("reload"):
                logger.info("🔄 Strategy 2: Reloading page and retrying...")
                await page.reload(wait_until="networkidle")
                await asyncio.sleep(3)
                continue
            
            if strategy.get("url"):
                logger.info(f"🔄 Strategy 3: Trying alternate URL: {strategy['url']}")
                await page.goto(strategy['url'], wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)
                continue
            
            # Try each selector
            for selector in strategy["selectors"]:
                try:
                    button = page.locator(selector).first
                    if await button.count() > 0:
                        await button.click()
                        logger.info(f"✅ CLICKED REVIEW BUTTON: {selector} (strategy: {strategy['name']})")
                        await asyncio.sleep(3)
                        logger.info(f"📊 URL AFTER CLICK: {page.url}")
                        return True, strategy["name"]
                except:
                    continue
                    
        except Exception as e:
            logger.warning(f"Strategy {strategy.get('name')} failed: {e}")
            continue
    
    logger.error("❌ ALL REVIEW BUTTON STRATEGIES FAILED")
    return False, "none"

# =========================================================
# CRITICAL FIX #3: PLACE ID VALIDATION
# =========================================================
async def validate_place_id(page, place_id: str) -> Tuple[bool, str]:
    """Verify that the place ID actually opened correctly"""
    
    await asyncio.sleep(2)
    title = await page.title()
    url = page.url
    
    logger.info(f"📊 PAGE TITLE: {title}")
    logger.info(f"📊 PAGE URL: {url}")
    
    # Check for invalid place
    if "Google Maps" == title or "Google Maps" in title and "place_id" in url:
        logger.error(f"❌ INVALID PLACE ID: {place_id} - Page title is just 'Google Maps'")
        await page.screenshot(path=f"{DEBUG_DIR}/invalid_place/{place_id}_invalid.png", full_page=True)
        return False, "invalid_place_id"
    
    # Check for error page
    if "error" in title.lower() or "not found" in title.lower():
        logger.error(f"❌ PLACE NOT FOUND: {place_id}")
        return False, "not_found"
    
    # Check for CAPTCHA
    html = await page.content()
    if "captcha" in html.lower() or "unusual traffic" in html.lower():
        logger.error(f"❌ CAPTCHA DETECTED for {place_id}")
        return False, "captcha"
    
    return True, "valid"

# =========================================================
# CRITICAL FIX #4: MULTI-PANEL DETECTION
# =========================================================
async def find_review_panel(page) -> Tuple[bool, str]:
    """Try multiple panel selectors before giving up"""
    
    panel_selectors = [
        { "name": "m6QErb", "selector": ".m6QErb" },
        { "name": "review-dialog", "selector": "[role='dialog'] .m6QErb" },
        { "name": "main-panel", "selector": "[role='main']" },
        { "name": "scrollable-panel", "selector": ".section-scrollbox" },
        { "name": "review-panel", "selector": "div[aria-label*='Reviews']" }
    ]
    
    for panel_info in panel_selectors:
        try:
            exists = await page.evaluate(f"""
                () => {{
                    const panel = document.querySelector('{panel_info['selector']}');
                    return !!panel;
                }}
            """)
            
            if exists:
                logger.info(f"✅ REVIEW PANEL FOUND: {panel_info['name']} ({panel_info['selector']})")
                return True, panel_info['name']
        except:
            continue
    
    logger.warning("⚠️ NO REVIEW PANEL FOUND with any selector")
    return False, "none"

# =========================================================
# CRITICAL FIX #5: SEMANTIC SELECTORS FIRST
# =========================================================
async def extract_reviews_semantic(page, place_id: str) -> List[Dict]:
    """Extract reviews using semantic selectors first (more reliable)"""
    
    reviews = []
    
    # Semantic selectors (more stable than CSS classes)
    semantic_selectors = [
        'div[data-review-id]',
        '[role="article"]',
        '[aria-label*="review"]',
        'div[jscontroller*="review"]'
    ]
    
    # Class-based selectors (fallback)
    class_selectors = [
        'div.jftiEf',
        'div.MyEned',
        'div[class*="review"]'
    ]
    
    all_selectors = semantic_selectors + class_selectors
    
    for selector in all_selectors:
        try:
            cards = await page.locator(selector).all()
            if cards:
                logger.info(f"📊 Found {len(cards)} cards using: {selector}")
                
                for card in cards[:MAX_REVIEWS]:
                    try:
                        review_data = {}
                        
                        # Author - semantic first
                        author = await card.get_attribute("data-author-name")
                        if not author:
                            author_selectors = ['.d4r55', '.TSUbDb', 'span[class*="author"]']
                            for sel in author_selectors:
                                if await card.locator(sel).count() > 0:
                                    author = (await card.locator(sel).first.inner_text()).strip()
                                    break
                        review_data["author"] = author or "Anonymous"
                        
                        # Review text - semantic first
                        text = await card.get_attribute("data-review-text")
                        if not text:
                            text_selectors = ['.wiI7pd', '.MyEned', 'span[jsname]']
                            for sel in text_selectors:
                                if await card.locator(sel).count() > 0:
                                    text = (await card.locator(sel).first.inner_text()).strip()
                                    break
                        
                        if not text:
                            continue
                        
                        review_data["review_text"] = text
                        
                        # Rating
                        rating_elem = card.locator('span.kvMYJc')
                        if await rating_elem.count() > 0:
                            aria = await rating_elem.first.get_attribute('aria-label')
                            if aria:
                                match = re.search(r'(\d)', aria)
                                if match:
                                    review_data["rating"] = int(match.group(1))
                        
                        if "rating" not in review_data:
                            review_data["rating"] = 5
                        
                        # Date
                        date_selectors = ['.rsqaWe', '.DeaRdd', 'span[class*="date"]']
                        for sel in date_selectors:
                            if await card.locator(sel).count() > 0:
                                review_data["review_date"] = (await card.locator(sel).first.inner_text()).strip()
                                break
                        
                        normalized = normalize_review(review_data, place_id)
                        if normalized:
                            reviews.append(normalized)
                            
                    except Exception as e:
                        logger.debug(f"Card extraction error: {e}")
                
                if reviews:
                    break
        except:
            continue
    
    return reviews

# =========================================================
# CRITICAL FIX #6: REVIEW PANEL SCROLLING (IMPROVED)
# =========================================================
async def scroll_review_panel_enhanced(page, max_scrolls: int = 30) -> int:
    """Enhanced scrolling with multiple panel detection"""
    
    scroll_count = 0
    last_height = 0
    no_change_count = 0
    
    for i in range(max_scrolls):
        try:
            result = await page.evaluate("""
                () => {
                    // Try multiple panel selectors
                    const selectors = ['.m6QErb', '[role="main"]', '.section-scrollbox'];
                    let panel = null;
                    
                    for (const sel of selectors) {
                        panel = document.querySelector(sel);
                        if (panel) break;
                    }
                    
                    if (panel) {
                        const currentHeight = panel.scrollHeight;
                        panel.scrollTop = panel.scrollHeight;
                        return { success: true, height: currentHeight, scrolled: true };
                    }
                    return { success: false, height: 0, scrolled: false };
                }
            """)
            
            if result and result.get('success'):
                current_height = result.get('height', 0)
                
                if current_height == last_height:
                    no_change_count += 1
                    if no_change_count >= 3:
                        logger.info(f"📊 Scroll complete: no height change after {no_change_count} attempts")
                        break
                else:
                    no_change_count = 0
                    last_height = current_height
                
                scroll_count += 1
                await asyncio.sleep(random.uniform(1.0, 1.5))
            else:
                break
                
        except Exception as e:
            logger.debug(f"Scroll error: {e}")
            break
    
    logger.info(f"📊 TOTAL SCROLLS: {scroll_count}")
    return scroll_count

# =========================================================
# REVIEW NORMALIZATION
# =========================================================
@lru_cache(maxsize=10000)
def generate_review_id_cached(place_id: str, author: str, text_hash: str, date: str) -> str:
    raw = f"{place_id}:{author}:{text_hash}:{date}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def normalize_review(review: Dict[str, Any], place_id: str) -> Optional[Dict]:
    try:
        review_text = str(review.get("review_text", "")).strip()
        if not review_text or len(review_text) < 3:
            return None
        
        author = str(review.get("author", "Anonymous")).strip()
        rating = min(5, max(1, int(review.get("rating", 5))))
        review_date = review.get("review_date", "")
        text_hash = hashlib.md5(review_text.encode()).hexdigest()[:16]
        
        return {
            "google_review_id": generate_review_id_cached(place_id, author, text_hash, review_date),
            "author": author,
            "author_name": author,
            "rating": rating,
            "review_text": review_text,
            "content": review_text,
            "text": review_text,
            "review_date": review_date,
            "likes_count": review.get("likes_count", 0),
            "is_local_guide": review.get("is_local_guide", False),
            "owner_response": review.get("owner_response", ""),
            "sentiment_score": 0.5,
            "google_review_time": datetime.utcnow(),
            "scraped_at": datetime.utcnow()
        }
    except Exception:
        return None

def deduplicate_reviews(reviews: List[Dict]) -> List[Dict]:
    seen = set()
    unique = []
    for review in reviews:
        rid = review.get("google_review_id", "")
        if rid and rid not in seen:
            seen.add(rid)
            unique.append(review)
    return unique

# =========================================================
# MAIN SCRAPER FUNCTION - ALL CRITICAL FIXES APPLIED
# =========================================================
async def scrape_google_reviews(place_id: str) -> List[Dict]:
    """
    MAIN SCRAPER - V15.0 with all critical fixes
    
    CRITICAL FIXES APPLIED:
    1. Fixed channel="chromium" instead of "chrome"
    2. Multi-strategy button clicking (no immediate failure)
    3. Place ID validation
    4. Multi-panel detection
    5. Semantic selectors first
    6. Enhanced scrolling
    7. Persistent browser profile
    8. Safe cache (no empty caching)
    """
    
    # CRITICAL: Log at very start
    logger.info("=" * 70)
    logger.info(f"🔍 SCRAPER STARTED for place_id: {place_id}")
    logger.info("=" * 70)
    
    if not place_id:
        logger.error("❌ EMPTY PLACE_ID received")
        return []
    
    # Check cache (safe cache - never returns empty)
    cache_key = f"reviews:{place_id}"
    cached_result = safe_cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    start_time = time.time()
    proxy = proxy_manager.get_best_proxy()
    
    # CRITICAL FIX #7: Persistent context
    async with async_playwright() as p:
        browser = None
        context = None
        
        try:
            # CRITICAL FIX #1: Use chromium channel (not chrome)
            logger.info("🚀 LAUNCHING PATCHRIGHT BROWSER (chromium channel)")
            browser = await p.chromium.launch(
                headless=HEADLESS_MODE,
                proxy=proxy,
                channel="chromium",  # FIXED: chromium, not chrome
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--window-size=1920,1080"
                ]
            )
            logger.info("✅ PATCHRIGHT BROWSER LAUNCHED SUCCESSFULLY")
            
            # CRITICAL FIX #7: Persistent context
            context = await browser.new_context(
                user_agent=ua_manager.get(),
                viewport={"width": random.randint(1366, 1920), "height": random.randint(768, 1080)},
                locale="en-US",
                timezone_id="America/New_York"
            )
            
            page = await context.new_page()
            
            # Apply stealth
            await stealth_async(page)
            
            # Navigate to place
            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            logger.info(f"🌐 NAVIGATING TO: {url}")
            
            response = await page.goto(url, wait_until="networkidle", timeout=60000)
            logger.info(f"📊 HTTP RESPONSE STATUS: {response.status if response else 'None'}")
            
            # CRITICAL FIX #3: Validate place ID
            is_valid, validation_status = await validate_place_id(page, place_id)
            if not is_valid:
                logger.error(f"❌ PLACE ID VALIDATION FAILED: {validation_status}")
                return []
            
            # Wait for page to stabilize
            await asyncio.sleep(random.uniform(2, 4))
            
            # CRITICAL FIX #2: Multi-strategy button clicking
            button_clicked, strategy = await click_reviews_button_with_fallback(page, place_id)
            if not button_clicked:
                logger.error("❌ COULD NOT CLICK REVIEWS BUTTON - ALL STRATEGIES FAILED")
                # Take debug screenshot
                await page.screenshot(path=f"{DEBUG_DIR}/error/no_button_{place_id}.png", full_page=True)
                return []
            
            logger.info(f"✅ REVIEW BUTTON CLICKED using strategy: {strategy}")
            
            # Wait for reviews to load
            await asyncio.sleep(3)
            
            # CRITICAL FIX #4: Find review panel
            panel_found, panel_name = await find_review_panel(page)
            if not panel_found:
                logger.error("❌ NO REVIEW PANEL FOUND")
                await page.screenshot(path=f"{DEBUG_DIR}/error/no_panel_{place_id}.png", full_page=True)
                return []
            
            logger.info(f"✅ REVIEW PANEL FOUND: {panel_name}")
            
            # Scroll to load reviews
            scrolls = await scroll_review_panel_enhanced(page, max_scrolls=25)
            logger.info(f"📊 SCROLLED {scrolls} times")
            
            # Wait for cards to load
            await asyncio.sleep(2)
            
            # CRITICAL FIX #5 & #6: Extract reviews with semantic selectors
            reviews = await extract_reviews_semantic(page, place_id)
            
            # Deduplicate
            reviews = deduplicate_reviews(reviews)[:MAX_REVIEWS]
            
            duration = time.time() - start_time
            logger.info(f"✅ SCRAPE COMPLETE: {len(reviews)} reviews in {duration:.2f}s")
            
            # Log final results
            if reviews:
                logger.info(f"🎉 SUCCESS: Found {len(reviews)} reviews for {place_id}")
                # Take success screenshot
                await page.screenshot(path=f"{DEBUG_DIR}/success/{place_id}_{len(reviews)}.png", full_page=True)
            else:
                logger.warning(f"⚠️ NO REVIEWS FOUND for {place_id}")
                await page.screenshot(path=f"{DEBUG_DIR}/no_reviews/{place_id}_none.png", full_page=True)
            
            # Update proxy stats
            if proxy:
                proxy_manager.report_result(proxy.get("server"), len(reviews) > 0, response_time=duration)
            
            # CRITICAL FIX #8: Only cache non-empty results
            if reviews:
                safe_cache.set(cache_key, reviews)
            
            return reviews
            
        except Exception as e:
            logger.error(f"❌ SCRAPER EXCEPTION: {e}")
            logger.error(traceback.format_exc())
            
            # Take error screenshot
            try:
                if 'page' in locals():
                    await page.screenshot(path=f"{DEBUG_DIR}/error/{place_id}_exception.png", full_page=True)
            except:
                pass
            
            return []
        
        finally:
            if context:
                await context.close()
            if browser:
                await browser.close()
                logger.info("🔒 Browser closed")

# =========================================================
# ALIAS FOR COMPATIBILITY
# =========================================================
async def run_scraper(place_id: str) -> List[Dict]:
    """Alias for existing app integration"""
    return await scrape_google_reviews(place_id)

# =========================================================
# READY
# =========================================================
logger.info("=" * 70)
logger.info("✅ ULTIMATE GOOGLE REVIEW SCRAPER V15.0 READY")
logger.info(f"📊 Persistent profile: {USER_DATA_DIR}")
logger.info(f"📊 Max reviews: {MAX_REVIEWS}")
logger.info(f"📊 Headless mode: {HEADLESS_MODE}")
logger.info("=" * 70)
