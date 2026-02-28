# FILE: app/services/places.py

from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
import requests

# ─────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────
logger = logging.getLogger("places")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────
# API Key Resolution
# ─────────────────────────────────────────────────────────────
def _resolve_places_api_key() -> Tuple[Optional[str], str]:
    """
    Prefer GOOGLE_PLACES_API_KEY; fall back to GOOGLE_MAPS_API_KEY.
    """
    key = os.getenv("GOOGLE_PLACES_API_KEY")
    if key:
        return key, "GOOGLE_PLACES_API_KEY"
    alt = os.getenv("GOOGLE_MAPS_API_KEY")
    if alt:
        logger.warning("Falling back to GOOGLE_MAPS_API_KEY → Places API")
        return alt, "GOOGLE_MAPS_API_KEY"
    return None, "NONE"


API_KEY, API_SRC = _resolve_places_api_key()

# Default timeouts (connect, read)
TIMEOUT = (5, 10)

# ─────────────────────────────────────────────────────────────
# Tiny in-process TTL Cache (best-effort)
# ─────────────────────────────────────────────────────────────
CACHE_TTL = int(os.getenv("PLACES_CACHE_TTL", "60"))  # seconds; 0 disables
_cache: Dict[Tuple[str, Tuple], Tuple[float, Any]] = {}


def _cache_get(ns: str, key: Tuple) -> Optional[Any]:
    if CACHE_TTL <= 0:
        return None
    k = (ns, key)
    item = _cache.get(k)
    if not item:
        return None
    ts, val = item
    if (time.time() - ts) < CACHE_TTL:
        return val
    _cache.pop(k, None)
    return None


def _cache_set(ns: str, key: Tuple, val: Any) -> None:
    if CACHE_TTL <= 0:
        return
    _cache[(ns, key)] = (time.time(), val)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _extract_city_from_components(components: List[Dict[str, Any]]) -> Optional[str]:
    """
    Returns best-effort city from address components.
    Prefers 'locality'; falls back to 'postal_town' or admin level 2.
    """
    city = None
    for comp in components or []:
        types = comp.get("types", [])
        if "locality" in types:
            return comp.get("long_name")
        if "postal_town" in types:
            city = city or comp.get("long_name")
        if "administrative_area_level_2" in types:
            city = city or comp.get("long_name")
    return city


def _require_key() -> str:
    if not API_KEY:
        raise RuntimeError("Google Places API key not configured")
    return API_KEY


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────
def autocomplete(
    query: str,
    *,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius: Optional[int] = 50000,
    language: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Places Autocomplete for establishments.

    Returns: [{ description, place_id }]
    """
    key = _require_key()
    cache_key = (query.strip().lower(), round(lat or 0, 4), round(lng or 0, 4), int(radius or 0), (language or "").lower())
    cached = _cache_get("ac", cache_key)
    if cached is not None:
        return cached

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params: Dict[str, Any] = {
        "input": query,
        "types": "establishment",
        "key": key,
    }
    if lat is not None and lng is not None:
        params["location"] = f"{lat},{lng}"
        if radius:
            params["radius"] = radius
    if language:
        params["language"] = language

    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            raise RuntimeError(f"Autocomplete error: {status}")
        out = [
            {"description": p.get("description"), "place_id": p.get("place_id")}
            for p in data.get("predictions", [])
        ]
        _cache_set("ac", cache_key, out)
        return out
    except Exception as e:
        logger.warning(f"Autocomplete failed: {e}")
        # graceful fallback: return empty list
        return []


def details(place_id: str, *, language: Optional[str] = None) -> Dict[str, Any]:
    """
    Places Details – normalized structure suitable for form autofill.

    Returns:
      {
        name, address, phone, website, city, lat, lng,
        rating, user_ratings_total, url
      }
    """
    key = _require_key()
    cache_key = (place_id, (language or "").lower())
    cached = _cache_get("details", cache_key)
    if cached is not None:
        return cached

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = ",".join([
        "name",
        "formatted_address",
        "formatted_phone_number",
        "international_phone_number",
        "website",
        "address_components",
        "geometry",
        "rating",
        "user_ratings_total",
        "url",
    ])
    params = {"place_id": place_id, "fields": fields, "key": key}
    if language:
        params["language"] = language

    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            raise RuntimeError(f"Details error: {status}")
        res = payload.get("result", {}) or {}

        loc = (res.get("geometry") or {}).get("location") or {}
        city = _extract_city_from_components(res.get("address_components", []))

        normalized = {
            "name": res.get("name"),
            "address": res.get("formatted_address"),
            "phone": res.get("formatted_phone_number") or res.get("international_phone_number"),
            "website": res.get("website"),
            "city": city,
            "lat": loc.get("lat"),
            "lng": loc.get("lng"),
            "rating": res.get("rating"),
            "user_ratings_total": res.get("user_ratings_total"),
            "url": res.get("url"),
        }
        _cache_set("details", cache_key, normalized)
        return normalized
    except Exception as e:
        logger.error(f"Details failed for {place_id}: {e}")
        return {}


def find_place(textquery: str, *, limit: int = 5, language: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Find Place from text query (like “Hotel Pearl Continental Lahore”).

    Returns: list of candidates enriched (best-effort) with details.
    """
    key = _require_key()
    cache_key = (textquery.strip().lower(), limit, (language or "").lower())
    cached = _cache_get("find", cache_key)
    if cached is not None:
        return cached

    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": textquery,
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address",
        "key": key,
    }
    if language:
        params["language"] = language

    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            raise RuntimeError(f"Find Place error: {status}")

        candidates = (data.get("candidates") or [])[:limit]
        items: List[Dict[str, Any]] = []
        for c in candidates:
            pid = c.get("place_id")
            det = details(pid, language=language) if pid else {}
            items.append({
                "name": det.get("name") or c.get("name"),
                "place_id": pid,
                "formatted_address": det.get("address") or c.get("formatted_address"),
                "city": det.get("city"),
                "rating": det.get("rating"),
                "user_ratings_total": det.get("user_ratings_total"),
                "location": {"lat": det.get("lat"), "lng": det.get("lng")} if det.get("lat") and det.get("lng") else None,
                "website": det.get("website"),
                "phone": det.get("phone"),
                "url": det.get("url"),
            })
        _cache_set("find", cache_key, items)
        return items
    except Exception as e:
        logger.error(f"Find Place failed for '{textquery}': {e}")
        return []
