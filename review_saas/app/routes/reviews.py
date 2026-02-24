from __future__ import annotations

import os
import sys
import time
import logging
from typing import Optional, Dict, List, Any, Tuple, Literal
from datetime import datetime, timedelta, timezone

import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from fastapi import APIRouter, Depends, HTTPException, Query, Header, Path, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..db import get_db
from ..models import Company, Review
from ..services.analysis import dashboard_payload

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# ─────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────
logger = logging.getLogger("reviews")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────
# Google API Keys
# ─────────────────────────────────────────────────────────────
GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY")
GOOGLE_BUSINESS_API_KEY: str = os.getenv("GOOGLE_BUSINESS_API_KEY")
GOOGLE_PLACES_API_KEY: str = os.getenv("GOOGLE_PLACES_API_KEY")
API_TOKEN = os.getenv("API_TOKEN")
REVIEWS_SCAN_LIMIT = int(os.getenv("REVIEWS_SCAN_LIMIT", "8000"))
_G_TIMEOUT: Tuple[int, int] = (5, 15)  # connect/read

# ─────────────────────────────────────────────────────────────
# Requests Session with Retry
# ─────────────────────────────────────────────────────────────
_google_sess: Optional[requests.Session] = None

def _google_session() -> requests.Session:
    global _google_sess
    if _google_sess:
        return _google_sess
    sess = requests.Session()
    retry = Retry(
        total=3, backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=50)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    _google_sess = sess
    return _google_sess

# ─────────────────────────────────────────────────────────────
# Google Places Helpers
# ─────────────────────────────────────────────────────────────
def _require_places_key():
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google Places API not configured")

def _google_places_get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        sess = _google_session()
        resp = sess.get(url, params=params, timeout=_G_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") not in ("OK", "ZERO_RESULTS"):
            logger.warning(f"Google Places API status: {payload.get('status')} | url={url}")
        return payload
    except requests.RequestException as e:
        logger.error(f"Google Places request failed: {e}")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "External API error")

def _extract_city_from_components(components: List[Dict[str, Any]]) -> Optional[str]:
    for comp in components:
        types = comp.get("types", [])
        if "locality" in types or "postal_town" in types or "administrative_area_level_2" in types:
            return comp.get("long_name")
    return None
