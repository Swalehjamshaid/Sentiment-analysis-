# ==========================================================
# FILE: app/services/scraper.py
# FINAL SAFE ENTERPRISE SCRAPER
# FULLY ALIGNED WITH:
# ✅ main.py
# ✅ reviews.py
# ✅ dashboard frontend
# ✅ Railway deployment
# ✅ Existing API routes
# ==========================================================

import os
import re
import gc
import time
import random
import asyncio
import hashlib
import logging
import traceback

from datetime import (
    datetime,
    timedelta
)

# ==========================================================
# SAFE IMPORTS
# ==========================================================

try:
    import requests
except Exception:
    requests = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from fake_useragent import UserAgent
except Exception:
    UserAgent = None

try:
    from playwright.async_api import async_playwright
except Exception:
    async_playwright = None

try:
    from playwright_stealth import stealth_async
except Exception:
    stealth_async = None

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    "app.services.scraper"
)

# ==========================================================
# ENV VARIABLES
# ==========================================================

SERPAPI_API_KEY = os.getenv(
    "SERPAPI_API_KEY"
)

PROXY_SERVER = os.getenv(
    "PROXY_SERVER"
)

PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME"
)

PROXY_PASSWORD = os.getenv(
    "PROXY_PASSWORD"
)

# ==========================================================
# CONFIG
# ==========================================================

REQUEST_TIMEOUT = 120
PLAYWRIGHT_TIMEOUT = 60000
HEADLESS = True
MAX_SCROLLS = 8

# ==========================================================
# SAFE USER AGENT
# ==========================================================

def get_user_agent():

    try:

        if UserAgent:

            return UserAgent().random

    except:
        pass

    return (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )

# ==========================================================
# CLEAN TEXT
# ==========================================================

def clean_text(text):

    if not text:
        return ""

    text = str(text)

    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.replace("\t", " ")

    return " ".join(text.split())[:5000]

# ==========================================================
# REVIEW HASH
# ==========================================================

def generate_hash(author, text):

    raw = f"{author}_{text}"

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()

# ==========================================================
# PROXY ROTATION
# ==========================================================

def get_proxy():

    try:

        session_id = random.randint(
            100000,
            999999
        )

        username = (
            f"{PROXY_USERNAME}-session-{session_id}"
        )

        return {

            "server":
                f"http://{PROXY_SERVER}",

            "username":
                username,

            "password":
                PROXY_PASSWORD
        }

    except:
        return None

# ==========================================================
# REQUESTS PROXY
# ==========================================================

def get_requests_proxy():

    try:

        session_id = random.randint(
            100000,
            999999
        )

        username = (
            f"{PROXY_USERNAME}-session-{session_id}"
        )

        proxy_url = (
            f"http://{username}:{PROXY_PASSWORD}@{PROXY_SERVER}"
        )

        return {

            "http": proxy_url,

            "https": proxy_url
        }

    except:
        return None

# ==========================================================
# DATE FILTER
# ==========================================================

def passes_date_filter(
    review_date,
    start_date=None
):

    try:

        if not start_date:
            return True

        lower = review_date.lower()

        now = datetime.utcnow()

        if "day" in lower:

            num = int(
                re.search(
                    r"\d+",
                    lower
                ).group()
            )

            actual = (
                now - timedelta(days=num)
            )

        elif "week" in lower:

            num = int(
                re.search(
                    r"\d+",
                    lower
                ).group()
            )

            actual = (
                now - timedelta(days=num * 7)
            )

        elif "month" in lower:

            num = int(
                re.search(
                    r"\d+",
                    lower
                ).group()
            )

            actual = (
                now - timedelta(days=num * 30)
            )

        elif "year" in lower:

            num = int(
                re.search(
                    r"\d+",
                    lower
                ).group()
            )

            actual = (
                now - timedelta(days=num * 365)
            )

        else:

            actual = now

        return actual >= start_date

    except:
        return True

# ==========================================================
# PLAYWRIGHT ENGINE
# ==========================================================

async def scrape_with_playwright(

    place_id,

    existing_ids=None,

    target_limit=40,

    start_date=None
):

    reviews = []

    existing_ids = existing_ids or set()

    if not async_playwright:

        logger.warning(
            "⚠️ PLAYWRIGHT NOT AVAILABLE"
        )

        return []

    browser = None

    try:

        async with async_playwright() as p:

            browser = await p.chromium.launch(

                headless=HEADLESS,

                proxy=get_proxy(),

                args=[

                    "--disable-blink-features=AutomationControlled",

                    "--disable-dev-shm-usage",
