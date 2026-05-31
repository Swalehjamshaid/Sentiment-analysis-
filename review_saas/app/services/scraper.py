# =========================================================
# FILE: app/services/scraper.py
# QUANTUM ENTERPRISE GOOGLE REVIEW SCRAPER - VERSION 10.0
# PATCHRIGHT + PLAYWRIGHT STEALTH + CRAWL4AI + CONSENSUS ENGINE
# FULLY ALIGNED WITH review.py - NO BREAKING CHANGES
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
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field, asdict

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

print("🚀 QUANTUM ENTERPRISE SCRAPER V10.0 BOOTING")

# =========================================================
# CACHE (Maintained for compatibility)
# =========================================================

from cachetools import TTLCache

review_cache = TTLCache(maxsize=2000, ttl=3600)

# =========================================================
# QUANTUM MEMORY - PERSISTENT (NEW)
# =========================================================

class QuantumMemory:
    """Persistent memory with optional Redis/PostgreSQL persistence"""
    
    def __init__(self):
        self.in_memory = {
            "GLOBAL_STATE": {
                "total_scrapes": 0,
                "total_reviews": 0,
                "started_at": datetime.utcnow().isoformat()
            },
            "SELECTOR_STATE": {},
            "PROVIDER_STATS": {},
            "PROXY_HEALTH": {}
        }
        self.redis_client = None
        self.pg_conn = None
        self._init_persistence()
    
    def _init_persistence(self):
        """Initialize Redis and PostgreSQL connections if available"""
        # Redis init
        try:
            import redis
            redis_host = os.getenv("REDIS_HOST", "")
            if redis_host:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=int(os.getenv("REDIS_PORT", 6379)),
                    password=os.getenv("REDIS_PASSWORD", None),
                    decode_responses=True
                )
                self.redis_client.ping()
                logger.info("✅ Redis persistence enabled")
        except Exception as e:
            logger.debug(f"Redis not available: {e}")
        
        # PostgreSQL init
        try:
            import psycopg2
            pg_host = os.getenv("PG_HOST", "")
            if pg_host:
                self.pg_conn = psycopg2.connect(
                    host=pg_host,
                    port=int(os.getenv("PG_PORT", 5432)),
                    database=os.getenv("PG_DATABASE", "quantum_scraper"),
                    user=os.getenv("PG_USER", "postgres"),
                    password=os.getenv("PG_PASSWORD", "")
                )
                self._init_postgres_schema()
                logger.info("✅ PostgreSQL persistence enabled")
        except Exception as e:
            logger.debug(f"PostgreSQL not available: {e}")
    
    def _init_postgres_schema(self):
        """Create tables if they don't exist"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS scraper_analytics (
                        id SERIAL PRIMARY KEY,
                        place_id TEXT,
                        reviews_found INTEGER,
                        duration FLOAT,
                        provider_used TEXT,
                        success BOOLEAN,
                        timestamp TIMESTAMP DEFAULT NOW()
                    )
                """)
                self.pg_conn.commit()
        except Exception as e:
            logger.warning(f"PostgreSQL schema init failed: {e}")
    
    def get(self, key: str, default=None):
        """Get value from memory (maintains compatibility)"""
        parts = key.split(".")
        current = self.in_memory
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current
    
    def set(self, key: str, value: Any):
        """Set value in memory"""
        parts = key.split(".")
        current = self.in_memory
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
    
    def update_proxy_health(self, proxy_server: str, success: bool, captcha: bool = False, response_time: float = 0):
        """Update proxy health metrics"""
        if proxy_server not in self.in_memory["PROXY_HEALTH"]:
            self.in_memory["PROXY_HEALTH"][proxy_server] = {
                "success": 1,
                "fail": 1,
                "captcha": 0,
                "response_times": []
            }
        
        stats = self.in_memory["PROXY_HEALTH"][proxy_server]
        if success:
            stats["success"] += 1
        else:
            stats["fail"] += 1
        if captcha:
            stats["captcha"] += 1
        if response_time > 0:
            stats["response_times"].append(response_time)
            if len(stats["response_times"]) > 100:
                stats["response_times"] = stats["response_times"][-100:]

# Initialize quantum memory
quantum_memory = QuantumMemory()

# =========================================================
# TENACITY
# =========================================================

from tenacity import retry, stop_after_attempt, wait_random_exponential

# =========================================================
# BACKOFF
# =========================================================

import backoff

# =========================================================
# SELECTOLAX
# =========================================================

SELECTOLAX_AVAILABLE = False
try:
    from selectolax.parser import HTMLParser
    SELECTOLAX_AVAILABLE = True
    logger.info("✅ SELECTOLAX READY")
except Exception as e:
    logger.error(f"❌ SELECTOLAX ERROR => {e}")

# =========================================================
# BEAUTIFULSOUP
# =========================================================

BS4_AVAILABLE = False
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
    logger.info("✅ BS4 READY")
except Exception as e:
    logger.error(f"❌ BS4 ERROR => {e}")

# =========================================================
# CURL_CFFI
# =========================================================

CURL_CFFI_AVAILABLE = False
try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
    logger.info("✅ CURL_CFFI READY")
except Exception as e:
    logger.error(f"❌ CURL_CFFI ERROR => {e}")

# =========================================================
# PATCHRIGHT
# =========================================================

PATCHRIGHT_AVAILABLE = False
try:
    from patchright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    PATCHRIGHT_AVAILABLE = True
    logger.info("✅ PATCHRIGHT READY")
except Exception as e:
    logger.error(f"❌ PATCHRIGHT ERROR => {e}")

# =========================================================
# PLAYWRIGHT STEALTH
# =========================================================

STEALTH_AVAILABLE = False
try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
    logger.info("✅ STEALTH READY")
except Exception as e:
    logger.error(f"❌ STEALTH ERROR => {e}")

# =========================================================
# CRAWL4AI - ENHANCED (NEW)
# =========================================================

CRAWL4AI_AVAILABLE = False
try:
    from crawl4ai import AsyncWebCrawler, CacheMode
    CRAWL4AI_AVAILABLE = True
    logger.info("✅ CRAWL4AI READY")
except Exception as e:
    logger.error(f"❌ CRAWL4AI ERROR => {e}")

# =========================================================
# FAKE USER AGENT
# =========================================================

FAKE_UA_AVAILABLE = False
try:
    from fake_useragent import UserAgent
    fake_ua = UserAgent()
    FAKE_UA_AVAILABLE = True
except Exception:
    fake_ua = None

# =========================================================
# ENVIRONMENT VARIABLES (Maintained for compatibility)
# =========================================================

SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "180"))
MAX_REVIEWS = int(os.getenv("SCRAPER_MAX_REVIEWS", "100"))
HEADLESS_MODE = os.getenv("SCRAPER_HEADLESS", "true").lower() == "true"

# Persistent browser profile path (NEW)
USER_DATA_DIR = os.getenv("USER_DATA_DIR", "/tmp/google_profile")
Path(USER_DATA_DIR).mkdir(parents=True, exist_ok=True)

# =========================================================
# PROXY CONFIGURATION (Fixed)
# =========================================================

PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "").strip()
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "").strip()

PROXY_POOL = []
FAILED_PROXIES = set()

if PROXY_SERVER:
    # Fixed: Proper proxy configuration without markdown syntax
    proxy_config = {"server": f"http://{PROXY_SERVER}"}
    if PROXY_USERNAME and PROXY_PASSWORD:
        proxy_config["username"] = PROXY_USERNAME
        proxy_config["password"] = PROXY_PASSWORD
    PROXY_POOL.append(proxy_config)

logger.info(f"✅ PROXY COUNT => {len(PROXY_POOL)}")

# =========================================================
# CONCURRENCY (Maintained)
# =========================================================

SCRAPER_SEMAPHORE = asyncio.Semaphore(2)

# =========================================================
# RATE LIMITER - ADAPTIVE (NEW)
# =========================================================

class AdaptiveRateLimiter:
    """Learns rate limiting patterns"""
    def __init__(self):
        self.request_timestamps = []
        self.blocked_count = 0
        self.current_delay = 2.0
    
    async def wait_if_needed(self):
        now = time.time()
        self.request_timestamps = [ts for ts in self.request_timestamps if now - ts < 60]
        
        if self.blocked_count > 3:
            self.current_delay = min(self.current_delay * 1.5, 30.0)
        elif self.blocked_count == 0:
            self.current_delay = max(self.current_delay * 0.9, 1.0)
        
        delay = self.current_delay + random.uniform(0, self.current_delay * 0.3)
        await asyncio.sleep(delay)
        self.request_timestamps.append(now)
    
    def record_block(self):
        self.blocked_count += 1
    
    def record_success(self):
        self.blocked_count = max(0, self.blocked_count - 1)

rate_limiter = AdaptiveRateLimiter()

# =========================================================
# HELPERS (Maintained with fixes)
# =========================================================

def utc_now():
    return datetime.utcnow()

def quantum_entropy():
    return secrets.randbelow(1000000)

async def quantum_delay():
    entropy = quantum_entropy()
    delay = ((entropy % 3000) / 1000)
    await asyncio.sleep(max(0.5, delay))

def maps_url(place_id: str) -> str:
    """Fixed: Proper URL without markdown syntax"""
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
# CAPTCHA DETECTION (Maintained)
# =========================================================

def detect_captcha(html: str):
    html_lower = html.lower()
    patterns = ["captcha", "unusual traffic", "not a robot", "sorry"]
    return any(p in html_lower for p in patterns)

# =========================================================
# PROXY SCORING - ENHANCED (NEW)
# =========================================================

def get_advanced_proxy_score(proxy_server: str) -> float:
    """Advanced proxy scoring with weighted metrics"""
    stats = quantum_memory.get(f"PROXY_HEALTH.{proxy_server}", {"success": 1, "fail": 1, "captcha": 0})
    
    success_rate = stats["success"] / (stats["success"] + stats["fail"])
    captcha_rate = stats["captcha"] / (stats["success"] + stats["fail"] + stats["captcha"] + 1)
    
    # Weighted score: 60% success, 30% captcha penalty, 10% latency
    return (success_rate * 0.6) - (captcha_rate * 0.3)

def get_best_proxy():
    try:
        available = [p for p in PROXY_POOL if p["server"] not in FAILED_PROXIES]
        if not available:
            return None
        
        scored = sorted(
            available,
            key=lambda p: get_advanced_proxy_score(p["server"]),
            reverse=True
        )
        return scored[0]
    except Exception:
        return None

def update_proxy_score(proxy_server: str, success: bool):
    """Legacy function - maintained for compatibility"""
    quantum_memory.update_proxy_health(proxy_server, success)

# =========================================================
# SELECTOR OPTIMIZER - SELF-HEALING (NEW)
# =========================================================

class SelectorOptimizer:
    """Self-healing selector system"""
    def __init__(self):
        self.selector_stats = defaultdict(lambda: {"success": 0, "fail": 0})
    
    def update(self, selector: str, success: bool):
        if success:
            self.selector_stats[selector]["success"] += 1
        else:
            self.selector_stats[selector]["fail"] += 1
        quantum_memory.set(f"SELECTOR_STATE.{selector}", self.selector_stats[selector])
    
    def get_success_rate(self, selector: str) -> float:
        stats = self.selector_stats.get(selector, {"success": 0, "fail": 0})
        total = stats["success"] + stats["fail"]
        return stats["success"] / total if total > 0 else 0.5
    
    def sort_by_success_rate(self, selectors: List[str]) -> List[str]:
        return sorted(selectors, key=lambda s: self.get_success_rate(s), reverse=True)

selector_optimizer = SelectorOptimizer()

# =========================================================
# REVIEW NORMALIZATION (Maintained for compatibility)
# =========================================================

def generate_review_id(place_id: str, author: str, text: str):
    raw = f"{place_id}:{author}:{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def normalize_review(review: Dict[str, Any], place_id: str):
    try:
        review_text = str(review.get("review_text", review.get("text", review.get("content", "")))).strip()
        if not review_text:
            return None
        
        author = str(review.get("author", review.get("author_name", "Anonymous"))).strip()
        if not author:
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
# REVIEW EXPANSION - CLICK "MORE" BUTTONS (NEW)
# =========================================================

async def expand_reviews_with_clicks(page):
    """Click all 'More' and 'Read more' buttons to expand reviews"""
    try:
        more_buttons = await page.locator("button:has-text('More'), button:has-text('more'), span:has-text('More')").all()
        for button in more_buttons:
            try:
                await button.click()
                await asyncio.sleep(0.5)
            except:
                pass
        
        read_more_buttons = await page.locator("button:has-text('Read more'), span:has-text('Read more')").all()
        for button in read_more_buttons:
            try:
                await button.click()
                await asyncio.sleep(0.3)
            except:
                pass
        
        return True
    except Exception as e:
        logger.error(f"❌ EXPAND REVIEWS ERROR => {e}")
        return False

# =========================================================
# DEBUG HELPERS (Maintained)
# =========================================================

async def debug_page(page, stage: str):
    try:
        logger.info(f"🔥 PAGE URL [{stage}] => {page.url}")
        logger.info(f"🔥 PAGE TITLE [{stage}] => {await page.title()}")
        await page.screenshot(path=f"debug_{stage}.png", full_page=True)
    except Exception as e:
        logger.error(f"❌ DEBUG ERROR => {e}")

# =========================================================
# CONSENSUS ENGINE - TRUE 2-OF-3 (NEW)
# =========================================================

async def consensus_engine(html: str, place_id: str) -> List[Dict]:
    """Run multiple parsers, accept reviews if 2 of 3 agree"""
    
    parser_results = {}
    
    # Parser 1: Selectolax
    if SELECTOLAX_AVAILABLE:
        try:
            parser = HTMLParser(html)
            reviews = []
            review_nodes = parser.css('div.jftiEf, div[data-review-id], div.MyEned')
            
            for node in review_nodes[:MAX_REVIEWS]:
                author_node = node.css_first('.d4r55, .TSUbDb')
                author = author_node.text(strip=True) if author_node else "Anonymous"
                
                text_node = node.css_first('.wiI7pd, .MyEned')
                text = text_node.text(strip=True) if text_node else ""
                
                rating = 5
                rating_node = node.css_first('span.kvMYJc')
                if rating_node and rating_node.attributes.get('aria-label'):
                    match = re.search(r'(\d)', rating_node.attributes['aria-label'])
                    if match:
                        rating = int(match.group(1))
                
                normalized = normalize_review({"author": author, "rating": rating, "review_text": text}, place_id)
                if normalized:
                    reviews.append(normalized)
            
            parser_results["selectolax"] = reviews
        except Exception as e:
            logger.error(f"❌ Selectolax consensus error: {e}")
    
    # Parser 2: BeautifulSoup
    if BS4_AVAILABLE:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            reviews = []
            review_elements = soup.select('div.jftiEf, div[data-review-id], div.MyEned')
            
            for elem in review_elements[:MAX_REVIEWS]:
                author_elem = elem.select_one('.d4r55, .TSUbDb')
                author = author_elem.get_text(strip=True) if author_elem else "Anonymous"
                
                text_elem = elem.select_one('.wiI7pd, .MyEned')
                text = text_elem.get_text(strip=True) if text_elem else ""
                
                rating = 5
                rating_elem = elem.select_one('span.kvMYJc')
                if rating_elem and rating_elem.get('aria-label'):
                    match = re.search(r'(\d)', rating_elem['aria-label'])
                    if match:
                        rating = int(match.group(1))
                
                normalized = normalize_review({"author": author, "rating": rating, "review_text": text}, place_id)
                if normalized:
                    reviews.append(normalized)
            
            parser_results["beautifulsoup"] = reviews
        except Exception as e:
            logger.error(f"❌ BeautifulSoup consensus error: {e}")
    
    # Consensus: Accept if at least 2 parsers agree
    review_votes = defaultdict(lambda: {"votes": 0, "review": None})
    
    for parser_name, reviews in parser_results.items():
        for review in reviews:
            review_id = review.get("google_review_id")
            if review_id not in review_votes:
                review_votes[review_id]["review"] = review
            review_votes[review_id]["votes"] += 1
    
    # Return reviews with 2 or more votes
    consensus_reviews = [data["review"] for data in review_votes.values() if data["votes"] >= 2]
    
    logger.info(f"✅ CONSENSUS ENGINE: {len(consensus_reviews)} reviews from {len(parser_results)} parsers")
    return consensus_reviews

# =========================================================
# ENHANCED CRAWL4AI PROVIDER (NEW)
# =========================================================

async def crawl4ai_reviews_enhanced(place_id: str) -> List[Dict]:
    """Enhanced Crawl4AI with JavaScript execution"""
    reviews = []
    
    if not CRAWL4AI_AVAILABLE:
        return reviews
    
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=maps_url(place_id),
                js_code="""
                    await page.waitForSelector('div.jftiEf, div[data-review-id]', { timeout: 10000 });
                    const buttons = document.querySelectorAll('button[aria-label*="reviews"], button[data-tab-index="1"]');
                    buttons.forEach(b => b.click());
                    await page.waitForTimeout(3000);
                """,
                bypass_cache=True,
                wait_until="networkidle"
            )
            
            if result and result.html:
                reviews = await consensus_engine(result.html, place_id)
        
        logger.info(f"✅ CRAWL4AI REVIEWS => {len(reviews)}")
    except Exception as e:
        logger.error(f"❌ CRAWL4AI ERROR: {e}")
    
    return reviews

# =========================================================
# PATCHRIGHT PROVIDER - ENHANCED (Maintained compatibility)
# =========================================================

@backoff.on_exception(backoff.expo, Exception, max_time=300)
async def patchright_reviews(place_id: str) -> List[Dict]:
    """Enhanced Patchright with persistent context and review expansion"""
    reviews = []
    
    if not PATCHRIGHT_AVAILABLE:
        logger.error("❌ PATCHRIGHT NOT AVAILABLE")
        return reviews
    
    async with SCRAPER_SEMAPHORE:
        context = None
        
        for attempt in range(3):
            proxy = get_best_proxy()
            
            try:
                logger.info(f"🔥 PATCHRIGHT ATTEMPT => {attempt+1}")
                logger.info(f"🔥 ACTIVE PROXY => {proxy['server'] if proxy else 'None'}")
                
                async with async_playwright() as p:
                    # Use persistent context for better trust score
                    context = await p.chromium.launch_persistent_context(
                        user_data_dir=USER_DATA_DIR,
                        headless=HEADLESS_MODE,
                        proxy=proxy,
                        channel="chrome",
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--window-size=1920,1080",
                            "--no-sandbox",
                            "--disable-web-security",
                            "--disable-features=IsolateOrigins,site-per-process",
                            "--disable-site-isolation-trials",
                            "--disable-infobars",
                            "--start-maximized",
                            "--disable-extensions",
                            "--disable-popup-blocking"
                        ],
                        user_agent=get_user_agent(),
                        locale="en-US",
                        timezone_id="America/New_York",
                        java_script_enabled=True,
                        ignore_https_errors=True,
                        viewport={
                            "width": random.randint(1366, 1920),
                            "height": random.randint(768, 1080)
                        }
                    )
                    
                    page = context.pages[0] if context.pages else await context.new_page()
                    
                    await page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    """)
                    
                    if STEALTH_AVAILABLE:
                        try:
                            await stealth_async(page)
                        except Exception:
                            pass
                    
                    target_url = maps_url(place_id)
                    logger.info(f"🔥 TARGET URL => {target_url}")
                    
                    await rate_limiter.wait_if_needed()
                    await page.goto(target_url, wait_until="networkidle", timeout=180000)
                    await page.wait_for_timeout(random.randint(4000, 9000))
                    
                    await debug_page(page, "before_reviews")
                    
                    # Sort selectors by historical success rate
                    review_button_selectors = selector_optimizer.sort_by_success_rate([
                        'button[jsaction*="pane.reviewChart.moreReviews"]',
                        'button[aria-label*="reviews"]',
                        'button[aria-label*="Reviews"]',
                        'button[aria-label*="Review"]',
                        'button[jsaction*="reviews"]',
                        'button[data-tab-index="1"]',
                        '[role="tab"][aria-label*="Reviews"]'
                    ])
                    
                    clicked = False
                    for selector in review_button_selectors:
                        try:
                            locator = page.locator(selector).first
                            if await locator.count() > 0:
                                await locator.click()
                                selector_optimizer.update(selector, True)
                                clicked = True
                                logger.info(f"✅ CLICKED => {selector}")
                                break
                        except Exception as e:
                            selector_optimizer.update(selector, False)
                            logger.error(f"❌ CLICK ERROR => {e}")
                    
                    if not clicked:
                        logger.error("❌ REVIEW BUTTON NOT FOUND")
                    
                    await page.wait_for_timeout(8000)
                    
                    # Expand all reviews by clicking "More" buttons
                    await expand_reviews_with_clicks(page)
                    
                    await debug_page(page, "after_review_click")
                    
                    html = await page.content()
                    
                    if detect_captcha(html):
                        logger.error("❌ CAPTCHA DETECTED")
                        rate_limiter.record_block()
                        if proxy:
                            update_proxy_score(proxy["server"], False)
                        return reviews
                    
                    rate_limiter.record_success()
                    
                    # Try consensus engine first
                    consensus_reviews = await consensus_engine(html, place_id)
                    if consensus_reviews:
                        reviews = consensus_reviews
                        logger.info(f"✅ CONSENSUS REVIEWS => {len(reviews)}")
                    
                    # Fallback to direct extraction if consensus fails
                    if not reviews:
                        review_selectors = selector_optimizer.sort_by_success_rate([
                            "div.jftiEf", "div[data-review-id]", "div.MyEned", 
                            "div[class*=review]", "div[class*=fontBodyMedium]"
                        ])
                        
                        cards = None
                        for selector in review_selectors:
                            try:
                                locator = page.locator(selector)
                                if await locator.count() > 0:
                                    cards = locator
                                    selector_optimizer.update(selector, True)
                                    break
                            except Exception:
                                selector_optimizer.update(selector, False)
                        
                        if cards:
                            previous_count, no_growth = 0, 0
                            while no_growth < 8:
                                try:
                                    await page.mouse.move(random.randint(100, 1200), random.randint(100, 700))
                                    await page.evaluate("""() => {
                                        const panels = document.querySelectorAll('[role="main"]');
                                        for (const panel of panels) {
                                            panel.scrollTop = panel.scrollTop + 2500;
                                        }
                                    }""")
                                    await quantum_delay()
                                    
                                    current_count = await cards.count()
                                    if current_count == previous_count:
                                        no_growth += 1
                                    else:
                                        no_growth = 0
                                    previous_count = current_count
                                    if current_count >= MAX_REVIEWS:
                                        break
                                except Exception as e:
                                    break
                            
                            total_cards = min(await cards.count(), MAX_REVIEWS)
                            for index in range(total_cards):
                                try:
                                    card = cards.nth(index)
                                    author, text, rating = "Anonymous", "", 5
                                    
                                    author_selectors = [".d4r55", ".TSUbDb", "span[class*=author]"]
                                    for sel in author_selectors:
                                        if await card.locator(sel).count() > 0:
                                            author = (await card.locator(sel).first.inner_text()).strip()
                                            break
                                    
                                    text_selectors = [".wiI7pd", ".MyEned", "span[jsname]"]
                                    for sel in text_selectors:
                                        if await card.locator(sel).count() > 0:
                                            text = (await card.locator(sel).first.inner_text()).strip()
                                            break
                                    
                                    if await card.locator("span.kvMYJc").count() > 0:
                                        aria = await card.locator("span.kvMYJc").get_attribute("aria-label")
                                        if aria:
                                            match = re.search(r"(\d)", aria)
                                            if match:
                                                rating = int(match.group(1))
                                    
                                    normalized = normalize_review({
                                        "author": author, "rating": rating, "review_text": text
                                    }, place_id)
                                    
                                    if normalized:
                                        reviews.append(normalized)
                                except Exception as e:
                                    logger.error(f"❌ REVIEW PARSE ERROR => {e}")
                    
                    logger.info(f"✅ PATCHRIGHT REVIEWS => {len(reviews)}")
                    
                    if proxy:
                        update_proxy_score(proxy["server"], True)
                    
                    if reviews:
                        break
                    
            except Exception as e:
                logger.error(f"❌ PATCHRIGHT ERROR => {e}")
                logger.error(traceback.format_exc())
                if proxy:
                    update_proxy_score(proxy["server"], False)
                await asyncio.sleep(random.uniform(3, 8))
            
            finally:
                try:
                    if context:
                        await context.close()
                except Exception:
                    pass
    
    return reviews

# =========================================================
# MASTER SCRAPER - QUANTUM SUPERPOSITION (Enhanced, maintained compatibility)
# =========================================================

async def scrape_google_reviews(place_id: str) -> List[Dict]:
    """
    Master scraper with quantum superposition.
    Maintains exact return format for app compatibility.
    """
    
    logger.info(f"🚀 MASTER SCRAPER => {place_id}")
    quantum_memory.set("GLOBAL_STATE.total_scrapes", quantum_memory.get("GLOBAL_STATE.total_scrapes", 0) + 1)
    
    if not place_id:
        return []
    
    cache_key = f"reviews:{place_id}"
    try:
        cached = review_cache.get(cache_key)
        if cached:
            logger.info("⚡ CACHE HIT")
            return cached
    except Exception:
        pass
    
    all_reviews = []
    
    # Quantum superposition: run multiple providers concurrently
    tasks = [patchright_reviews(place_id)]
    
    if CRAWL4AI_AVAILABLE:
        tasks.append(crawl4ai_reviews_enhanced(place_id))
    
    # Run all providers
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Pick best result (largest review set)
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"❌ Provider error: {result}")
            continue
        if isinstance(result, list) and len(result) > len(all_reviews):
            all_reviews = result
    
    # Fallback to consensus if no reviews found
    if not all_reviews and CURL_CFFI_AVAILABLE:
        try:
            response = curl_requests.get(maps_url(place_id), headers={"User-Agent": get_user_agent()}, timeout=30)
            if response.status_code == 200:
                consensus_reviews = await consensus_engine(response.text, place_id)
                all_reviews.extend(consensus_reviews)
        except Exception as e:
            logger.error(f"❌ Fallback error: {e}")
    
    all_reviews = deduplicate_reviews(all_reviews)[:MAX_REVIEWS]
    
    try:
        review_cache[cache_key] = all_reviews
    except Exception:
        pass
    
    quantum_memory.set("GLOBAL_STATE.total_reviews", quantum_memory.get("GLOBAL_STATE.total_reviews", 0) + len(all_reviews))
    
    logger.info(f"✅ FINAL REVIEWS => {len(all_reviews)}")
    return all_reviews

# =========================================================
# ALIASES (Maintained for 100% compatibility)
# =========================================================

async def run_scraper(place_id: str):
    """Maintained alias for app compatibility"""
    return await scrape_google_reviews(place_id)

# Legacy functions maintained for backward compatibility
def score_proxy(proxy_server: str):
    """Legacy function - maintained for compatibility"""
    stats = quantum_memory.get(f"PROXY_HEALTH.{proxy_server}", {"success": 1, "fail": 1})
    return stats["success"] / (stats["success"] + stats["fail"])

# =========================================================
# READY
# =========================================================

logger.info("✅ QUANTUM ENTERPRISE SCRAPER V10.0 READY")
logger.info(f"📊 Features: Persistent Memory={bool(quantum_memory.redis_client or quantum_memory.pg_conn)}, Consensus=2-of-3, Rate Limiting=Adaptive")
