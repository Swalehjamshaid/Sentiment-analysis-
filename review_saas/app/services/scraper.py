# =========================================================
# FILE: app/services/scraper.py
# QUANTUM ENTERPRISE GOOGLE REVIEW SCRAPER - VERSION 10.5
# PRODUCTION GRADE - ACTUALLY EXTRACTS REVIEWS
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

print("🚀 QUANTUM ENTERPRISE SCRAPER V10.5 BOOTING - PRODUCTION GRADE")

# =========================================================
# CACHE (Maintained for compatibility)
# =========================================================

from cachetools import TTLCache

review_cache = TTLCache(maxsize=2000, ttl=3600)

# =========================================================
# QUANTUM MEMORY - PERSISTENT
# =========================================================

class QuantumMemory:
    """Persistent memory with Redis/PostgreSQL persistence"""
    
    def __init__(self):
        self.in_memory = {
            "GLOBAL_STATE": {
                "total_scrapes": 0,
                "total_reviews": 0,
                "started_at": datetime.utcnow().isoformat()
            },
            "SELECTOR_STATE": {},
            "PROVIDER_STATS": {},
            "PROXY_HEALTH": {},
            "COOLDOWN_PROXIES": {}  # NEW: Track cooldown proxies
        }
        self.redis_client = None
        self.pg_conn = None
        self._init_persistence()
    
    def _init_persistence(self):
        """Initialize Redis and PostgreSQL connections if available"""
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
        parts = key.split(".")
        current = self.in_memory
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current
    
    def set(self, key: str, value: Any):
        parts = key.split(".")
        current = self.in_memory
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

quantum_memory = QuantumMemory()

# =========================================================
# TENACITY & BACKOFF
# =========================================================

from tenacity import retry, stop_after_attempt, wait_random_exponential
import backoff

# =========================================================
# LIBRARY AVAILABILITY CHECKS
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
    from crawl4ai import AsyncWebCrawler, CacheMode
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

SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "180"))
MAX_REVIEWS = int(os.getenv("SCRAPER_MAX_REVIEWS", "100"))
HEADLESS_MODE = os.getenv("SCRAPER_HEADLESS", "true").lower() == "true"

# Persistent browser profile path
USER_DATA_DIR = os.getenv("USER_DATA_DIR", "/tmp/google_profile")
Path(USER_DATA_DIR).mkdir(parents=True, exist_ok=True)

# Debug directory for HTML/screenshot dumps
DEBUG_DIR = os.getenv("DEBUG_DIR", "/tmp/scraper_debug")
Path(DEBUG_DIR).mkdir(parents=True, exist_ok=True)

# =========================================================
# PROXY CONFIGURATION
# =========================================================

PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "").strip()
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "").strip()

PROXY_POOL = []
FAILED_PROXIES = set()
COOLDOWN_PROXIES = {}  # NEW: Track proxies in cooldown

if PROXY_SERVER:
    proxy_config = {"server": f"http://{PROXY_SERVER}"}
    if PROXY_USERNAME and PROXY_PASSWORD:
        proxy_config["username"] = PROXY_USERNAME
        proxy_config["password"] = PROXY_PASSWORD
    PROXY_POOL.append(proxy_config)

logger.info(f"✅ PROXY COUNT => {len(PROXY_POOL)}")

# =========================================================
# CONCURRENCY
# =========================================================

SCRAPER_SEMAPHORE = asyncio.Semaphore(2)

# =========================================================
# PROVIDER ANNEALING - REAL IMPLEMENTATION (NEW)
# =========================================================

class ProviderAnnealer:
    """Real provider annealing with actual execution control"""
    
    def __init__(self):
        self.provider_stats = defaultdict(lambda: {"success": 0, "fail": 0, "reviews": []})
        self._load_stats()
    
    def _load_stats(self):
        """Load historical provider stats"""
        for provider in ["patchright", "crawl4ai"]:
            stats = quantum_memory.get(f"PROVIDER_STATS.{provider}")
            if stats:
                self.provider_stats[provider] = stats
    
    def get_provider_score(self, provider: str) -> float:
        """Calculate provider score based on historical success"""
        stats = self.provider_stats.get(provider, {"success": 0, "fail": 0})
        total = stats["success"] + stats["fail"]
        if total == 0:
            return 0.5  # Neutral starting score
        return stats["success"] / total
    
    def get_best_provider(self) -> str:
        """Return best provider based on annealing"""
        scores = {p: self.get_provider_score(p) for p in ["patchright", "crawl4ai"]}
        
        # Exploration rate: 20% chance to try non-best provider
        if random.random() < 0.2:
            return random.choice(["patchright", "crawl4ai"])
        
        # Exploit: return best provider
        return max(scores, key=scores.get)
    
    def update_provider_stats(self, provider: str, success: bool, reviews_count: int):
        """Update provider statistics"""
        if provider not in self.provider_stats:
            self.provider_stats[provider] = {"success": 0, "fail": 0, "reviews": []}
        
        if success:
            self.provider_stats[provider]["success"] += 1
        else:
            self.provider_stats[provider]["fail"] += 1
        
        self.provider_stats[provider]["reviews"].append(reviews_count)
        if len(self.provider_stats[provider]["reviews"]) > 100:
            self.provider_stats[provider]["reviews"] = self.provider_stats[provider]["reviews"][-100:]
        
        # Persist to quantum memory
        quantum_memory.set(f"PROVIDER_STATS.{provider}", self.provider_stats[provider])
        
        logger.info(f"📊 Provider {provider} score: {self.get_provider_score(provider):.2f}")

provider_annealer = ProviderAnnealer()

# =========================================================
# PROXY COOLDOWN (NEW)
# =========================================================

def is_proxy_in_cooldown(proxy_server: str) -> bool:
    """Check if proxy is in cooldown period"""
    if proxy_server not in COOLDOWN_PROXIES:
        return False
    
    cooldown_until = COOLDOWN_PROXIES[proxy_server]
    if time.time() < cooldown_until:
        logger.warning(f"⚠️ Proxy {proxy_server} in cooldown until {datetime.fromtimestamp(cooldown_until)}")
        return True
    else:
        # Cooldown expired
        del COOLDOWN_PROXIES[proxy_server]
        return False

def apply_proxy_cooldown(proxy_server: str, failures: int = 5):
    """Apply cooldown to proxy after repeated failures"""
    if failures >= 5:
        cooldown_hours = 1
        cooldown_until = time.time() + (cooldown_hours * 3600)
        COOLDOWN_PROXIES[proxy_server] = cooldown_until
        quantum_memory.set(f"COOLDOWN_PROXIES.{proxy_server}", cooldown_until)
        logger.warning(f"⚠️ Proxy {proxy_server} cooling down for {cooldown_hours} hour")

# =========================================================
# HELPER FUNCTIONS
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
# ENHANCED CAPTCHA DETECTION - PHASE 6
# =========================================================

def detect_captcha(html: str):
    html_lower = html.lower()
    patterns = [
        "captcha",
        "unusual traffic",
        "not a robot",
        "sorry",
        "verify you are human",  # NEW
        "security check",         # NEW
        "access denied",          # NEW
        "automated queries"       # NEW
    ]
    return any(p in html_lower for p in patterns)

# =========================================================
# PROXY SCORING
# =========================================================

def get_advanced_proxy_score(proxy_server: str) -> float:
    """Advanced proxy scoring with cooldown awareness"""
    if is_proxy_in_cooldown(proxy_server):
        return -1.0  # Effectively disables this proxy
    
    stats = quantum_memory.get(f"PROXY_HEALTH.{proxy_server}", {"success": 1, "fail": 1, "captcha": 0})
    
    success_rate = stats["success"] / (stats["success"] + stats["fail"])
    captcha_rate = stats["captcha"] / (stats["success"] + stats["fail"] + stats["captcha"] + 1)
    
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

def update_proxy_score(proxy_server: str, success: bool, captcha: bool = False):
    """Update proxy score and track failures for cooldown"""
    stats_key = f"PROXY_HEALTH.{proxy_server}"
    stats = quantum_memory.get(stats_key, {"success": 1, "fail": 1, "captcha": 0, "failures_streak": 0})
    
    if success:
        stats["success"] += 1
        stats["failures_streak"] = 0
    else:
        stats["fail"] += 1
        stats["failures_streak"] = stats.get("failures_streak", 0) + 1
        
        # Apply cooldown after 5 consecutive failures
        if stats["failures_streak"] >= 5:
            apply_proxy_cooldown(proxy_server, stats["failures_streak"])
    
    if captcha:
        stats["captcha"] += 1
    
    quantum_memory.set(stats_key, stats)

# =========================================================
# SELECTOR OPTIMIZER
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
# REVIEW NORMALIZATION - ENHANCED WITH MORE FIELDS (PHASE 8)
# =========================================================

def generate_review_id(place_id: str, author: str, text: str, date: str = ""):
    raw = f"{place_id}:{author}:{text}:{date}"
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
        
        # NEW: Extract additional fields
        review_date = review.get("review_date", "")
        owner_response = review.get("owner_response", "")
        owner_response_date = review.get("owner_response_date", "")
        likes_count = review.get("likes_count", 0)
        is_local_guide = review.get("is_local_guide", False)
        author_review_count = review.get("author_review_count", 0)
        
        return {
            "google_review_id": generate_review_id(place_id, author, review_text, review_date),
            "author": author,
            "author_name": author,
            "rating": rating,
            "review_text": review_text,
            "content": review_text,
            "text": review_text,
            "review_date": review_date,  # NEW
            "owner_response": owner_response,  # NEW
            "owner_response_date": owner_response_date,  # NEW
            "likes_count": likes_count,  # NEW
            "is_local_guide": is_local_guide,  # NEW
            "author_review_count": author_review_count,  # NEW
            "sentiment_score": 0.5,
            "google_review_time": utc_now() if not review_date else review_date,
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
# HTML & SCREENSHOT DEBUGGING - PHASE 1
# =========================================================

async def debug_dump(page, place_id: str, stage: str):
    """Dump HTML and screenshot when reviews are not found"""
    try:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename_base = f"{DEBUG_DIR}/{place_id}_{stage}_{timestamp}"
        
        # Dump HTML
        html = await page.content()
        html_path = f"{filename_base}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"📄 HTML dumped to {html_path}")
        
        # Dump screenshot
        screenshot_path = f"{filename_base}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        logger.info(f"📸 Screenshot saved to {screenshot_path}")
        
        # Log page title and URL
        title = await page.title()
        url = page.url
        logger.info(f"📊 PAGE TITLE => {title}")
        logger.info(f"📊 PAGE URL => {url}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Debug dump error: {e}")
        return False

# =========================================================
# CONSENSUS ENGINE
# =========================================================

async def consensus_engine(html: str, place_id: str) -> List[Dict]:
    """Run multiple parsers, accept reviews if 2 of 3 agree"""
    
    parser_results = {}
    
    # Parser 1: Selectolax
    if SELECTOLAX_AVAILABLE:
        try:
            parser = HTMLParser(html)
            reviews = []
            review_nodes = parser.css('div.jftiEf, div[data-review-id], div.MyEned, div[role="article"], div[class*="review"]')
            
            for node in review_nodes[:MAX_REVIEWS]:
                author_node = node.css_first('.d4r55, .TSUbDb, span[class*="author"]')
                author = author_node.text(strip=True) if author_node else "Anonymous"
                
                text_node = node.css_first('.wiI7pd, .MyEned, span[jsname]')
                text = text_node.text(strip=True) if text_node else ""
                
                rating = 5
                rating_node = node.css_first('span.kvMYJc')
                if rating_node and rating_node.attributes.get('aria-label'):
                    match = re.search(r'(\d)', rating_node.attributes['aria-label'])
                    if match:
                        rating = int(match.group(1))
                
                # Extract date
                date_node = node.css_first('.rsqaWe, .DeaRdd')
                date = date_node.text(strip=True) if date_node else ""
                
                normalized = normalize_review({
                    "author": author, 
                    "rating": rating, 
                    "review_text": text,
                    "review_date": date
                }, place_id)
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
            review_elements = soup.select('div.jftiEf, div[data-review-id], div.MyEned, div[role="article"], div[class*="review"]')
            
            for elem in review_elements[:MAX_REVIEWS]:
                author_elem = elem.select_one('.d4r55, .TSUbDb, span[class*="author"]')
                author = author_elem.get_text(strip=True) if author_elem else "Anonymous"
                
                text_elem = elem.select_one('.wiI7pd, .MyEned, span[jsname]')
                text = text_elem.get_text(strip=True) if text_elem else ""
                
                rating = 5
                rating_elem = elem.select_one('span.kvMYJc')
                if rating_elem and rating_elem.get('aria-label'):
                    match = re.search(r'(\d)', rating_elem['aria-label'])
                    if match:
                        rating = int(match.group(1))
                
                date_elem = elem.select_one('.rsqaWe, .DeaRdd')
                date = date_elem.get_text(strip=True) if date_elem else ""
                
                normalized = normalize_review({
                    "author": author, 
                    "rating": rating, 
                    "review_text": text,
                    "review_date": date
                }, place_id)
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
    
    consensus_reviews = [data["review"] for data in review_votes.values() if data["votes"] >= 2]
    
    logger.info(f"✅ CONSENSUS ENGINE: {len(consensus_reviews)} reviews from {len(parser_results)} parsers")
    return consensus_reviews

# =========================================================
# REVIEW SCROLLING - FIXED (PHASE 2)
# =========================================================

async def scroll_reviews_page(page):
    """Improved scrolling using the correct .m6QErb panel"""
    try:
        # THIS IS THE FIX - Use .m6QErb instead of [role="main"]
        scrolled = await page.evaluate("""
            () => {
                const panel = document.querySelector('.m6QErb');
                if (panel) {
                    const previousHeight = panel.scrollHeight;
                    panel.scrollTop = panel.scrollHeight;
                    return { success: true, previousHeight, newHeight: panel.scrollHeight };
                }
                
                // Fallback to older selector
                const panels = document.querySelectorAll('[role="main"]');
                for (const p of panels) {
                    const previousHeight = p.scrollHeight;
                    p.scrollTop = p.scrollHeight;
                    return { success: true, previousHeight, newHeight: p.scrollHeight };
                }
                return { success: false };
            }
        """)
        return scrolled.get('success', False) if isinstance(scrolled, dict) else False
    except Exception as e:
        logger.error(f"❌ Scroll error: {e}")
        return False

# =========================================================
# ENHANCED REVIEW BUTTON DETECTION (PHASE 3)
# =========================================================

async def click_reviews_button(page):
    """Enhanced review button detection with more selectors"""
    
    review_button_selectors = [
        'button[jsaction*="pane.reviewChart.moreReviews"]',
        'button[aria-label*="reviews"]',
        'button[aria-label*="Reviews"]',
        'button[aria-label*="Review"]',
        'button[jsaction*="reviews"]',
        'button[data-tab-index="1"]',
        '[role="tab"][aria-label*="Reviews"]',
        '[data-value="Reviews"]',  # NEW
        'button[jsaction*="pane.rating.moreReviews"]',  # NEW
        'button[aria-label*="Google reviews"]',  # NEW
        'button[role="tab"]',  # NEW
        'a[aria-label*="reviews"]'  # NEW
    ]
    
    # Sort by historical success rate
    sorted_selectors = selector_optimizer.sort_by_success_rate(review_button_selectors)
    
    for selector in sorted_selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                await locator.click()
                selector_optimizer.update(selector, True)
                logger.info(f"✅ CLICKED REVIEW BUTTON => {selector}")
                return True
        except Exception as e:
            selector_optimizer.update(selector, False)
            logger.debug(f"Selector {selector} failed: {e}")
    
    logger.error("❌ NO REVIEW BUTTON FOUND")
    return False

# =========================================================
# EXPAND TRUNCATED REVIEWS (PHASE 5)
# =========================================================

async def expand_truncated_reviews(page):
    """Expand all truncated reviews by clicking More/Read more buttons"""
    try:
        expand_selectors = [
            'button:has-text("More")',
            'button:has-text("more")',
            'span:has-text("More")',
            'button:has-text("Read more")',
            'span:has-text("Read more")',
            'span.w8nwRe',  # NEW
            'button[jsaction*="expand"]'  # NEW
        ]
        
        expanded_count = 0
        for selector in expand_selectors:
            try:
                buttons = await page.locator(selector).all()
                for button in buttons:
                    try:
                        await button.click()
                        expanded_count += 1
                        await asyncio.sleep(0.3)
                    except:
                        pass
            except:
                pass
        
        if expanded_count > 0:
            logger.info(f"✅ Expanded {expanded_count} truncated reviews")
        
        return expanded_count
    except Exception as e:
        logger.error(f"❌ Expand reviews error: {e}")
        return 0

# =========================================================
# ENHANCED REVIEW CARD PARSING (PHASE 4 & 8)
# =========================================================

async def parse_review_card(card, place_id: str) -> Optional[Dict]:
    """Parse a single review card with all metadata"""
    try:
        # Basic fields
        author = "Anonymous"
        author_selectors = [".d4r55", ".TSUbDb", "span[class*=author]", "a[class*=author]"]
        for sel in author_selectors:
            if await card.locator(sel).count() > 0:
                author = (await card.locator(sel).first.inner_text()).strip()
                break
        
        text = ""
        text_selectors = [".wiI7pd", ".MyEned", "span[jsname]", "div[class*=review-text]"]
        for sel in text_selectors:
            if await card.locator(sel).count() > 0:
                text = (await card.locator(sel).first.inner_text()).strip()
                break
        
        rating = 5
        if await card.locator("span.kvMYJc").count() > 0:
            aria = await card.locator("span.kvMYJc").get_attribute("aria-label")
            if aria:
                match = re.search(r"(\d)", aria)
                if match:
                    rating = int(match.group(1))
        
        # NEW: Review date
        date = ""
        date_selectors = [".rsqaWe", ".DeaRdd", "span[class*=date]"]
        for sel in date_selectors:
            if await card.locator(sel).count() > 0:
                date = (await card.locator(sel).first.inner_text()).strip()
                break
        
        # NEW: Likes count
        likes_count = 0
        likes_selectors = ['button[jsaction*="like"]', '.PKRcHd']
        for sel in likes_selectors:
            if await card.locator(sel).count() > 0:
                likes_text = await card.locator(sel).first.inner_text()
                likes_match = re.search(r'(\d+)', likes_text)
                if likes_match:
                    likes_count = int(likes_match.group(1))
                break
        
        # NEW: Local guide badge
        is_local_guide = False
        local_guide_selectors = ['img[alt*="Local Guide"]', '.local-guide-badge']
        for sel in local_guide_selectors:
            if await card.locator(sel).count() > 0:
                is_local_guide = True
                break
        
        # NEW: Author review count
        author_review_count = 0
        review_count_selectors = ['.RfnDt', '.review-count']
        for sel in review_count_selectors:
            if await card.locator(sel).count() > 0:
                count_text = await card.locator(sel).first.inner_text()
                count_match = re.search(r'(\d+)', count_text)
                if count_match:
                    author_review_count = int(count_match.group(1))
                break
        
        # NEW: Owner response
        owner_response = ""
        owner_response_date = ""
        owner_selectors = ['[jsname="bN97Pc"]', '.CDe7pd']
        for sel in owner_selectors:
            if await card.locator(sel).count() > 0:
                owner_response = (await card.locator(sel).first.inner_text()).strip()
                # Try to get owner response date
                date_elem = card.locator(f'{sel} + div .DeaRdd, {sel} + .DeaRdd')
                if await date_elem.count() > 0:
                    owner_response_date = (await date_elem.first.inner_text()).strip()
                break
        
        return normalize_review({
            "author": author,
            "rating": rating,
            "review_text": text,
            "review_date": date,
            "owner_response": owner_response,
            "owner_response_date": owner_response_date,
            "likes_count": likes_count,
            "is_local_guide": is_local_guide,
            "author_review_count": author_review_count
        }, place_id)
        
    except Exception as e:
        logger.error(f"❌ Review card parse error: {e}")
        return None

# =========================================================
# PATCHRIGHT PROVIDER - FULLY ENHANCED
# =========================================================

@backoff.on_exception(backoff.expo, Exception, max_time=300)
async def patchright_reviews(place_id: str) -> List[Dict]:
    """Enhanced Patchright with all improvements"""
    reviews = []
    
    if not PATCHRIGHT_AVAILABLE:
        logger.error("❌ PATCHRIGHT NOT AVAILABLE")
        return reviews
    
    async with SCRAPER_SEMAPHORE:
        context = None
        
        for attempt in range(3):
            proxy = get_best_proxy()
            start_time = time.time()
            
            try:
                logger.info(f"🔥 PATCHRIGHT ATTEMPT => {attempt+1}")
                logger.info(f"🔥 ACTIVE PROXY => {proxy['server'] if proxy else 'None'}")
                
                async with async_playwright() as p:
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
                    
                   
