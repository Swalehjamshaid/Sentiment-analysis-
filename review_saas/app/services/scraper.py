# =========================================================
# FILE: app/services/scraper.py
# QUANTUM ENTERPRISE GOOGLE REVIEW SCRAPER - V16.0
# ENHANCED WITH MULTI-STRATEGY EXTRACTION
# =========================================================

from __future__ import annotations

# =========================================================
# STANDARD LIBRARIES
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
import secrets
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict
from functools import lru_cache

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

print("🚀 QUANTUM ENTERPRISE SCRAPER V16.0 - ENHANCED EXTRACTION")

# =========================================================
# CACHE
# =========================================================

from cachetools import TTLCache

review_cache = TTLCache(maxsize=2000, ttl=3600)

# =========================================================
# TENACITY & BACKOFF
# =========================================================

from tenacity import retry, stop_after_attempt, wait_random_exponential
import backoff

# =========================================================
# LIBRARY AVAILABILITY
# =========================================================

SELECTOLAX_AVAILABLE = False
try:
    from selectolax.parser import HTMLParser
    SELECTOLAX_AVAILABLE = True
    logger.info("✅ SELECTOLAX READY")
except Exception as e:
    logger.error(f"❌ SELECTOLAX ERROR => {e}")

BS4_AVAILABLE = False
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
    logger.info("✅ BS4 READY")
except Exception as e:
    logger.error(f"❌ BS4 ERROR => {e}")

CURL_CFFI_AVAILABLE = False
try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
    logger.info("✅ CURL_CFFI READY")
except Exception as e:
    logger.error(f"❌ CURL_CFFI ERROR => {e}")

PATCHRIGHT_AVAILABLE = False
try:
    from patchright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    PATCHRIGHT_AVAILABLE = True
    logger.info("✅ PATCHRIGHT READY")
except Exception as e:
    logger.error(f"❌ PATCHRIGHT ERROR => {e}")

STEALTH_AVAILABLE = False
try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
    logger.info("✅ STEALTH READY")
except Exception as e:
    logger.error(f"❌ STEALTH ERROR => {e}")

CRAWL4AI_AVAILABLE = False
try:
    from crawl4ai import AsyncWebCrawler
    CRAWL4AI_AVAILABLE = True
    logger.info("✅ CRAWL4AI READY")
except Exception as e:
    logger.error(f"❌ CRAWL4AI ERROR => {e}")

FAKE_UA_AVAILABLE = False
try:
    from fake_useragent import UserAgent
    fake_ua = UserAgent()
    FAKE_UA_AVAILABLE = True
except Exception:
    fake_ua = None

# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "300"))
MAX_REVIEWS = int(os.getenv("SCRAPER_MAX_REVIEWS", "100"))
HEADLESS_MODE = os.getenv("SCRAPER_HEADLESS", "true").lower() == "true"

USER_DATA_DIR = os.getenv("USER_DATA_DIR", "/tmp/chrome_profile")
Path(USER_DATA_DIR).mkdir(parents=True, exist_ok=True)

# =========================================================
# PROXY CONFIGURATION (Enhanced)
# =========================================================

PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "").strip()
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "").strip()

PROXY_POOL = []
FAILED_PROXIES = set()
PROXY_HEALTH = {}

# Support multiple proxies
if "," in PROXY_SERVER:
    for proxy in PROXY_SERVER.split(","):
        proxy = proxy.strip()
        if proxy:
            PROXY_POOL.append({
                "server": f"http://{proxy}",
                "username": PROXY_USERNAME,
                "password": PROXY_PASSWORD
            })
elif PROXY_SERVER:
    PROXY_POOL.append({
        "server": f"http://{PROXY_SERVER}",
        "username": PROXY_USERNAME,
        "password": PROXY_PASSWORD
    })

logger.info(f"✅ PROXY COUNT => {len(PROXY_POOL)}")

# =========================================================
# CONCURRENCY
# =========================================================

SCRAPER_SEMAPHORE = asyncio.Semaphore(2)

# =========================================================
# ENHANCED DIAGNOSTICS
# =========================================================

class ScrapeDiagnostics:
    """Track detailed scrape diagnostics"""
    
    def __init__(self, place_id: str):
        self.place_id = place_id
        self.start_time = datetime.now()
        self.steps = []
        self.errors = []
        self.reviews_found = 0
        self.captcha_detected = False
        self.button_clicked = False
        self.panel_found = False
        self.cards_found = 0
    
    def add_step(self, step: str, success: bool = True, details: str = None):
        self.steps.append({
            "step": step,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
        if not success:
            logger.warning(f"⚠️ STEP FAILED: {step} - {details}")
        else:
            logger.info(f"✅ STEP PASSED: {step}")
    
    def add_error(self, error: str):
        self.errors.append(error)
        logger.error(f"❌ ERROR: {error}")
    
    def log_summary(self):
        duration = (datetime.now() - self.start_time).total_seconds()
        logger.info("=" * 50)
        logger.info(f"📊 SCRAPE SUMMARY for {self.place_id}")
        logger.info(f"   Duration: {duration:.2f}s")
        logger.info(f"   Reviews found: {self.reviews_found}")
        logger.info(f"   Steps passed: {sum(1 for s in self.steps if s['success'])}/{len(self.steps)}")
        logger.info(f"   Button clicked: {self.button_clicked}")
        logger.info(f"   Panel found: {self.panel_found}")
        logger.info(f"   Cards found: {self.cards_found}")
        logger.info(f"   Captcha: {self.captcha_detected}")
        if self.errors:
            logger.info(f"   Errors: {len(self.errors)}")
        logger.info("=" * 50)

# =========================================================
# ENHANCED CAPTCHA DETECTION
# =========================================================

def detect_captcha(html: str) -> Tuple[bool, str]:
    html_lower = html.lower()
    
    patterns = [
        ("captcha", "captcha"),
        ("unusual traffic", "traffic"),
        ("not a robot", "robot"),
        ("sorry", "sorry"),
        ("verify you are human", "verify"),
        ("security check", "security"),
        ("access denied", "denied"),
        ("automated queries", "automated"),
        ("rate limit", "rate")
    ]
    
    for pattern, name in patterns:
        if pattern in html_lower:
            return True, name
    
    return False, None

# =========================================================
# HELPERS
# =========================================================

def utc_now():
    return datetime.utcnow()

def quantum_entropy():
    return secrets.randbelow(1000000)

async def quantum_delay():
    entropy = quantum_entropy()
    delay = (entropy % 3000) / 1000
    await asyncio.sleep(max(0.5, delay))

def maps_url(place_id: str):
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"

def get_user_agent():
    static_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ]
    if FAKE_UA_AVAILABLE and fake_ua:
        try:
            return fake_ua.random
        except Exception:
            pass
    return random.choice(static_agents)

# =========================================================
# PROXY SCORING
# =========================================================

def score_proxy(proxy_server: str):
    stats = PROXY_HEALTH.get(proxy_server, {"success": 1, "fail": 1, "captcha": 0})
    success_rate = stats["success"] / (stats["success"] + stats["fail"])
    captcha_rate = stats["captcha"] / (stats["success"] + stats["fail"] + stats["captcha"] + 1)
    return (success_rate * 0.6) - (captcha_rate * 0.3)

def update_proxy_score(proxy_server: str, success: bool, captcha: bool = False):
    if proxy_server not in PROXY_HEALTH:
        PROXY_HEALTH[proxy_server] = {"success": 1, "fail": 1, "captcha": 0}
    
    if success:
        PROXY_HEALTH[proxy_server]["success"] += 1
    else:
        PROXY_HEALTH[proxy_server]["fail"] += 1
    
    if captcha:
        PROXY_HEALTH[proxy_server]["captcha"] += 1

def get_best_proxy():
    try:
        available = [p for p in PROXY_POOL if p["server"] not in FAILED_PROXIES]
        if not available:
            return None
        scored = sorted(available, key=lambda p: score_proxy(p["server"]), reverse=True)
        return scored[0]
    except Exception:
        return None

# =========================================================
# REVIEW NORMALIZATION
# =========================================================

def generate_review_id(place_id: str, author: str, text: str):
    raw = f"{place_id}:{author}:{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def normalize_review(review: Dict[str, Any], place_id: str):
    try:
        review_text = str(review.get("review_text", review.get("text", review.get("content", "")))).strip()
        if not review_text or len(review_text) < 3:
            return None

        author = str(review.get("author", review.get("author_name", "Anonymous"))).strip()
        if not author or len(author) > 100:
            author = "Anonymous"

        rating = review.get("rating", 5)
        try:
            rating = int(float(rating))
        except Exception:
            rating = 5
        rating = max(1, min(rating, 5))

        return {
            "google_review_id": generate_review_id(place_id, author, review_text),
            "author": author,
            "author_name": author,
            "rating": rating,
            "review_text": review_text,
            "content": review_text,
            "text": review_text,
            "sentiment_score": 0.5,
            "google_review_time": utc_now(),
            "scraped_at": utc_now()
        }
    except Exception as e:
        logger.error(f"❌ NORMALIZE ERROR => {e}")
        return None

def deduplicate_reviews(reviews: List[Dict]):
    seen = set()
    unique = []
    for review in reviews:
        review_id = review.get("google_review_id", "")
        if not review_id or review_id in seen:
            continue
        seen.add(review_id)
        unique.append(review)
    return unique

# =========================================================
# REVIEW BUTTON CLICKING - ENHANCED
# =========================================================

async def click_reviews_button_enhanced(page, diagnostics: ScrapeDiagnostics) -> bool:
    """Enhanced button clicking with multiple strategies"""
    
    # Strategy 1: Direct selectors
    button_selectors = [
        'button[jsaction*="pane.reviewChart.moreReviews"]',
        'button[aria-label*="reviews"]',
        'button[aria-label*="Reviews"]',
        'button[data-tab-index="1"]',
        '[role="tab"][aria-label*="Reviews"]',
        '[data-value="Reviews"]',
        'button[jsaction*="pane.rating.moreReviews"]',
        'button[aria-label*="Google reviews"]'
    ]
    
    for selector in button_selectors:
        try:
            button = page.locator(selector).first
            if await button.count() > 0:
                await button.click()
                diagnostics.button_clicked = True
                diagnostics.add_step("click_reviews_button", True, f"Selector: {selector}")
                logger.info(f"✅ CLICKED REVIEW BUTTON: {selector}")
                await asyncio.sleep(3)
                return True
        except Exception as e:
            continue
    
    # Strategy 2: Try scrolling to find button
    try:
        await page.evaluate("window.scrollTo(0, 500)")
        await asyncio.sleep(1)
        
        for selector in button_selectors:
            try:
                button = page.locator(selector).first
                if await button.count() > 0:
                    await button.click()
                    diagnostics.button_clicked = True
                    diagnostics.add_step("click_reviews_button", True, "After scroll")
                    logger.info("✅ CLICKED REVIEW BUTTON (after scroll)")
                    await asyncio.sleep(3)
                    return True
            except:
                continue
    except:
        pass
    
    diagnostics.add_step("click_reviews_button", False, "No button found")
    return False

# =========================================================
# REVIEW PANEL DETECTION - ENHANCED
# =========================================================

async def find_review_panel_enhanced(page, diagnostics: ScrapeDiagnostics) -> bool:
    """Enhanced panel detection with multiple strategies"""
    
    panel_selectors = [
        (".m6QErb", "classic"),
        ("[role='main']", "main"),
        (".section-scrollbox", "scrollbox"),
        ("[role='dialog'] .m6QErb", "dialog"),
        ("div[aria-label*='Reviews']", "aria")
    ]
    
    for selector, name in panel_selectors:
        try:
            panel = await page.evaluate(f"""
                () => {{
                    const el = document.querySelector('{selector}');
                    return !!el;
                }}
            """)
            if panel:
                diagnostics.panel_found = True
                diagnostics.add_step("find_review_panel", True, f"Selector: {selector} ({name})")
                logger.info(f"✅ REVIEW PANEL FOUND: {name}")
                return True
        except:
            continue
    
    diagnostics.add_step("find_review_panel", False, "No panel found")
    return False

# =========================================================
# REVIEW SCROLLING - ENHANCED
# =========================================================

async def scroll_reviews_enhanced(page, max_scrolls: int = 25) -> int:
    """Enhanced scrolling with proper panel detection"""
    
    scroll_count = 0
    last_height = 0
    no_change_count = 0
    
    for i in range(max_scrolls):
        try:
            result = await page.evaluate("""
                () => {
                    const panel = document.querySelector('.m6QErb') || 
                                 document.querySelector('[role="main"]') ||
                                 document.querySelector('.section-scrollbox');
                    
                    if (panel) {
                        const currentHeight = panel.scrollHeight;
                        panel.scrollTop = panel.scrollHeight;
                        return { success: true, height: currentHeight };
                    }
                    return { success: false };
                }
            """)
            
            if result and result.get('success'):
                current_height = result.get('height', 0)
                if current_height == last_height:
                    no_change_count += 1
                    if no_change_count >= 3:
                        break
                else:
                    no_change_count = 0
                    last_height = current_height
                
                scroll_count += 1
                await asyncio.sleep(random.uniform(1.0, 1.5))
            else:
                break
        except:
            break
    
    logger.info(f"📊 SCROLLED {scroll_count} times")
    return scroll_count

# =========================================================
# ALTERNATE URL SCRAPING (NEW)
# =========================================================

async def scrape_alternate_url(place_id: str, diagnostics: ScrapeDiagnostics) -> List[Dict]:
    """Try alternative Google Reviews URL"""
    
    reviews = []
    alt_urls = [
        f"https://search.google.com/local/reviews?placeid={place_id}",
        f"https://www.google.com/search?q={place_id}+google+reviews"
    ]
    
    async with async_playwright() as p:
        for alt_url in alt_urls:
            try:
                logger.info(f"🔄 Trying alternate URL: {alt_url}")
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(user_agent=get_user_agent())
                page = await context.new_page()
                
                await page.goto(alt_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)
                
                # Look for review-like content
                html = await page.content()
                
                # Parse with BeautifulSoup
                if BS4_AVAILABLE:
                    soup = BeautifulSoup(html, 'html.parser')
                    review_elements = soup.select('.g, .review, [data-review-id]')
                    
                    for elem in review_elements[:MAX_REVIEWS]:
                        text = elem.get_text(strip=True)
                        if len(text) > 50:  # Likely a review
                            review = normalize_review({
                                "author": "Google User",
                                "rating": 5,
                                "review_text": text[:500]
                            }, place_id)
                            if review:
                                reviews.append(review)
                
                await browser.close()
                
                if reviews:
                    diagnostics.add_step("alternate_url", True, f"Found {len(reviews)} reviews")
                    break
                    
            except Exception as e:
                logger.debug(f"Alternate URL failed: {e}")
                continue
    
    return reviews

# =========================================================
# MAIN PATCHRIGHT PROVIDER - ENHANCED
# =========================================================

@backoff.on_exception(backoff.expo, Exception, max_time=300)
async def patchright_reviews(place_id: str, diagnostics: ScrapeDiagnostics) -> List[Dict]:
    """Enhanced Patchright with full diagnostics"""
    
    reviews = []
    
    if not PATCHRIGHT_AVAILABLE:
        diagnostics.add_error("Patchright not available")
        return reviews
    
    async with SCRAPER_SEMAPHORE:
        context = None
        
        for attempt in range(3):
            proxy = get_best_proxy()
            
            try:
                logger.info(f"🔥 PATCHRIGHT ATTEMPT => {attempt+1}")
                
                async with async_playwright() as p:
                    # Launch with persistent context
                    context = await p.chromium.launch_persistent_context(
                        user_data_dir=USER_DATA_DIR,
                        headless=HEADLESS_MODE,
                        proxy=proxy,
                        channel="chromium",
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--window-size=1920,1080",
                            "--no-sandbox"
                        ]
                    )
                    
                    page = context.pages[0] if context.pages else await context.new_page()
                    
                    await page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    """)
                    
                    if STEALTH_AVAILABLE:
                        try:
                            await stealth_async(page)
                        except:
                            pass
                    
                    # Navigate to page
                    target_url = maps_url(place_id)
                    logger.info(f"🌐 TARGET URL => {target_url}")
                    diagnostics.add_step("navigate", True, target_url)
                    
                    response = await page.goto(target_url, wait_until="networkidle", timeout=60000)
                    
                    if response and response.status >= 400:
                        diagnostics.add_step("navigate", False, f"HTTP {response.status}")
                        continue
                    
                    await asyncio.sleep(random.randint(2, 4))
                    
                    # Check for CAPTCHA
                    html = await page.content()
                    is_captcha, captcha_type = detect_captcha(html)
                    if is_captcha:
                        diagnostics.captcha_detected = True
                        diagnostics.add_step("captcha_check", False, captcha_type)
                        if proxy:
                            update_proxy_score(proxy["server"], False, captcha=True)
                        continue
                    
                    diagnostics.add_step("captcha_check", True)
                    
                    # Click reviews button
                    button_clicked = await click_reviews_button_enhanced(page, diagnostics)
                    if not button_clicked:
                        diagnostics.add_step("button_click", False, "Could not find button")
                        continue
                    
                    await asyncio.sleep(3)
                    
                    # Find review panel
                    panel_found = await find_review_panel_enhanced(page, diagnostics)
                    if not panel_found:
                        diagnostics.add_step("panel_found", False, "No panel detected")
                        continue
                    
                    # Scroll to load reviews
                    scrolls = await scroll_reviews_enhanced(page, max_scrolls=20)
                    diagnostics.add_step("scrolling", True, f"{scrolls} scrolls")
                    
                    await asyncio.sleep(2)
                    
                    # Extract review cards
                    card_selectors = [
                        "div[data-review-id]",
                        "div.jftiEf",
                        "div.MyEned",
                        "[role='article']"
                    ]
                    
                    cards = None
                    for selector in card_selectors:
                        locator = page.locator(selector)
                        count = await locator.count()
                        if count > 0:
                            cards = locator
                            diagnostics.cards_found = count
                            diagnostics.add_step("find_cards", True, f"{count} cards with {selector}")
                            logger.info(f"📊 Found {count} cards with {selector}")
                            break
                    
                    if not cards:
                        diagnostics.add_step("find_cards", False, "No cards found")
                        continue
                    
                    # Extract reviews from cards
                    total_cards = min(await cards.count(), MAX_REVIEWS)
                    
                    for index in range(total_cards):
                        try:
                            card = cards.nth(index)
                            
                            # Extract author
                            author = "Anonymous"
                            author_selectors = [".d4r55", ".TSUbDb", "span[class*=author]"]
                            for sel in author_selectors:
                                if await card.locator(sel).count() > 0:
                                    author = (await card.locator(sel).first.inner_text()).strip()
                                    break
                            
                            # Extract text
                            text = ""
                            text_selectors = [".wiI7pd", ".MyEned", "span[jsname]"]
                            for sel in text_selectors:
                                if await card.locator(sel).count() > 0:
                                    text = (await card.locator(sel).first.inner_text()).strip()
                                    break
                            
                            if not text:
                                continue
                            
                            # Extract rating
                            rating = 5
                            rating_locator = card.locator("span.kvMYJc")
                            if await rating_locator.count() > 0:
                                aria = await rating_locator.get_attribute("aria-label")
                                if aria:
                                    match = re.search(r"(\d)", aria)
                                    if match:
                                        rating = int(match.group(1))
                            
                            normalized = normalize_review({
                                "author": author,
                                "rating": rating,
                                "review_text": text
                            }, place_id)
                            
                            if normalized:
                                reviews.append(normalized)
                                
                        except Exception as e:
                            logger.debug(f"Card parse error: {e}")
                    
                    diagnostics.reviews_found = len(reviews)
                    diagnostics.add_step("extract_reviews", True, f"{len(reviews)} reviews")
                    
                    logger.info(f"✅ EXTRACTED {len(reviews)} REVIEWS")
                    
                    if proxy:
                        update_proxy_score(proxy["server"], len(reviews) > 0)
                    
                    if reviews:
                        break
                    
            except Exception as e:
                logger.error(f"❌ PATCHRIGHT ERROR: {e}")
                diagnostics.add_error(str(e))
                if proxy:
                    update_proxy_score(proxy["server"], False)
                await asyncio.sleep(random.uniform(3, 8))
            
            finally:
                if context:
                    await context.close()
    
    return reviews

# =========================================================
# CRAWL4AI FALLBACK
# =========================================================

async def crawl4ai_fallback(place_id: str, diagnostics: ScrapeDiagnostics) -> List[Dict]:
    """Fallback to Crawl4AI if Patchright fails"""
    
    reviews = []
    
    if not CRAWL4AI_AVAILABLE:
        return reviews
    
    try:
        logger.info("🔄 Trying Crawl4AI fallback...")
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=maps_url(place_id),
                bypass_cache=True,
                wait_until="networkidle"
            )
            
            if result and result.html:
                if BS4_AVAILABLE:
                    soup = BeautifulSoup(result.html, 'html.parser')
                    review_elements = soup.select('div[data-review-id], div.jftiEf, div.MyEned')
                    
                    for elem in review_elements[:MAX_REVIEWS]:
                        text_elem = elem.select_one('.wiI7pd, .MyEned')
                        if text_elem:
                            text = text_elem.get_text(strip=True)
                            if text:
                                review = normalize_review({
                                    "author": "Anonymous",
                                    "rating": 5,
                                    "review_text": text
                                }, place_id)
                                if review:
                                    reviews.append(review)
        
        if reviews:
            diagnostics.add_step("crawl4ai_fallback", True, f"Found {len(reviews)} reviews")
            logger.info(f"✅ CRAWL4AI FOUND {len(reviews)} REVIEWS")
        else:
            diagnostics.add_step("crawl4ai_fallback", False, "No reviews found")
            
    except Exception as e:
        logger.debug(f"Crawl4AI fallback error: {e}")
    
    return reviews

# =========================================================
# MASTER SCRAPER - WITH ENHANCED LOGGING
# =========================================================

async def scrape_google_reviews(place_id: str) -> List[Dict]:
    """Enhanced master scraper with full diagnostics"""
    
    # Create diagnostics tracker
    diagnostics = ScrapeDiagnostics(place_id)
    
    logger.info(f"🚀 MASTER SCRAPER STARTING for {place_id}")
    diagnostics.add_step("scraper_start", True)
    
    if not place_id:
        diagnostics.add_error("Empty place_id")
        return []
    
    # Check cache (only return non-empty results)
    cache_key = f"reviews:{place_id}"
    try:
        cached = review_cache.get(cache_key)
        if cached and len(cached) > 0:
            logger.info(f"⚡ CACHE HIT: {len(cached)} reviews")
            diagnostics.add_step("cache_hit", True, f"{len(cached)} reviews")
            diagnostics.reviews_found = len(cached)
            diagnostics.log_summary()
            return cached
    except Exception as e:
        logger.debug(f"Cache error: {e}")
    
    all_reviews = []
    
    # Primary: Patchright
    try:
        result = await asyncio.wait_for(
            patchright_reviews(place_id, diagnostics),
            timeout=240
        )
        if isinstance(result, list):
            all_reviews.extend(result)
    except asyncio.TimeoutError:
        diagnostics.add_error("Patchright timeout after 240s")
        logger.error("❌ PATCHRIGHT TIMEOUT")
    except Exception as e:
        diagnostics.add_error(f"Patchright exception: {e}")
        logger.error(f"❌ PATCHRIGHT EXCEPTION: {e}")
    
    # If no reviews, try alternate URL
    if len(all_reviews) == 0 and CURL_CFFI_AVAILABLE:
        logger.info("🔄 Trying alternate URL extraction...")
        alt_reviews = await scrape_alternate_url(place_id, diagnostics)
        all_reviews.extend(alt_reviews)
    
    # If still no reviews, try Crawl4AI fallback
    if len(all_reviews) == 0 and CRAWL4AI_AVAILABLE:
        crawl_reviews = await crawl4ai_fallback(place_id, diagnostics)
        all_reviews.extend(crawl_reviews)
    
    # Deduplicate and limit
    all_reviews = deduplicate_reviews(all_reviews)[:MAX_REVIEWS]
    
    # Update diagnostics
    diagnostics.reviews_found = len(all_reviews)
    
    # Only cache non-empty results
    if all_reviews and len(all_reviews) > 0:
        try:
            review_cache[cache_key] = all_reviews
            logger.info(f"💾 CACHED {len(all_reviews)} reviews for {place_id}")
        except Exception as e:
            logger.debug(f"Cache set error: {e}")
    else:
        # Log warning but don't cache
        logger.info(f"⚠️ No reviews found for {place_id} - not caching")
        # Save debug info
        try:
            with open(f"{place_id}_no_reviews.log", "a") as f:
                f.write(f"{datetime.now().isoformat()} - No reviews found\n")
                f.write(f"Steps: {diagnostics.steps}\n")
                f.write(f"Errors: {diagnostics.errors}\n")
        except:
            pass
    
    # Log summary
    diagnostics.log_summary()
    logger.info(f"✅ FINAL REVIEWS => {len(all_reviews)}")
    
    return all_reviews

# =========================================================
# ALIAS
# =========================================================

async def run_scraper(place_id: str):
    return await scrape_google_reviews(place_id)

# =========================================================
# READY
# =========================================================

logger.info("✅ QUANTUM PATCHRIGHT SCRAPER V16.0 READY")
logger.info(f"📊 Persistent profile: {USER_DATA_DIR}")
logger.info(f"📊 Max reviews: {MAX_REVIEWS}")
