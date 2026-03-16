# filename: app/services/review.py
import logging
import hashlib
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

# Import your models from your core models file
from app.models import Company, Review

logger = logging.getLogger(__name__)

# --- Configuration ---
OUTSCRAPER_API_KEY = os.getenv("OUTSCRAPER_API_KEY", "").strip()
OUTSCRAPER_BASE_URL = os.getenv("OUTSCRAPER_BASE_URL", "https://api.app.outscraper.com").rstrip("/")
OUTSCRAPER_SEARCH_URL = f"{OUTSCRAPER_BASE_URL}/maps/search-v2"
OUTSCRAPER_REVIEWS_URL = f"{OUTSCRAPER_BASE_URL}/maps/reviews-v3"

HTTP_TIMEOUT = httpx.Timeout(20.0, read=60.0)
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3

# Fields mask for the search endpoint (so we get exactly what our schema needs)
SEARCH_FIELDS = (
    "query,name,full_address,site,phone,rating,reviews,latitude,longitude,place_id,google_id,cid"
)

# --- Small utilities ---

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

async def _request_with_retries(
    client: httpx.AsyncClient, method: str, url: str, *, params: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """HTTP with basic retries/backoff on transient errors."""
    headers = {"X-API-KEY": OUTSCRAPER_API_KEY}
    attempt = 0
    backoff = 1.0

    while True:
        attempt += 1
        try:
            resp = await client.request(method, url, headers=headers, params=params)
            if resp.status_code in RETRY_STATUS and attempt < MAX_RETRIES:
                logger.warning(
                    "Outscraper %s %s -> %s. Retrying in %.1fs (attempt %s/%s)",
                    method, url, resp.status_code, backoff, attempt, MAX_RETRIES
                )
                await asyncio.sleep(backoff)  # type: ignore  # asyncio is available in your runtime
                backoff *= 2
                continue
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"data": data}
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt >= MAX_RETRIES:
                logger.exception("HTTP timeout on %s %s after %s attempts", method, url, attempt)
                raise
            logger.warning("Timeout on %s %s. Retrying in %.1fs", method, url, backoff)
            await asyncio.sleep(backoff)  # type: ignore
            backoff *= 2
        except httpx.HTTPStatusError:
            logger.exception("HTTP error on %s %s", method, url)
            raise
        except Exception:
            logger.exception("Unexpected error on %s %s", method, url)
            raise

def _parse_review_datetime(review_item: Dict[str, Any]) -> datetime:
    # Prefer ISO field if present, else use epoch timestamp, else now
    dt_iso = review_item.get("review_datetime_utc") or review_item.get("datetime_utc")
    if dt_iso:
        try:
            # replace trailing Z if present for fromisoformat
            return datetime.fromisoformat(str(dt_iso).replace("Z", "+00:00"))
        except Exception:
            pass
    ts = review_item.get("review_timestamp") or review_item.get("timestamp")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except Exception:
            pass
    return _now_utc()

def _normalized_text(text: str) -> str:
    return " ".join((text or "").split()).strip()

def generate_review_hash(
    place_id: Optional[str],
    author_name: str,
    text: str,
    rating: Optional[int],
    created_at: datetime,
) -> str:
    """
    Stronger hash: include place_id and the review date to minimize collisions across companies
    and across time. Uses SHA-256 instead of MD5.
    """
    raw = "|".join([
        (place_id or "").strip(),
        (author_name or "").strip().lower(),
        str(rating if rating is not None else ""),
        _normalized_text(text),
        created_at.date().isoformat(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

# --- Outscraper: Companies (search/details) ---

async def fetch_company_from_outscaper(query: str) -> Dict[str, Any]:
    """
    Fetches exact business data from Outscraper `maps/search-v2`.
    Replaces Google Autocomplete/Details logic.
    """
    if not OUTSCRAPER_API_KEY:
        raise RuntimeError("OUTSCRAPER_API_KEY is not configured")

    params = {
        "query": query,
        "limit": 1,       # adjust if you want to list multiple candidates
        "async": "false",
        "fields": SEARCH_FIELDS,
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            data = await _request_with_retries(client, "GET", OUTSCRAPER_SEARCH_URL, params=params)
        except Exception as e:
            logger.error("Outscraper search error for query '%s': %s", query, e)
            return {}

    # Normalize: Outscraper commonly returns {"data": [ [ {...}, ... ] ]}
    items: List[Dict[str, Any]] = []
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        nested = data["data"]
        if nested and isinstance(nested[0], list):
            items = nested[0]
        elif nested and isinstance(nested[0], dict):
            items = nested

    if not items:
        return {}

    item = items[0]
    # Map to your schema field names:
    return {
        "name": item.get("name"),
        "full_address": item.get("full_address"),
        "site": item.get("site") or item.get("website"),
        "phone": item.get("phone"),
        "rating": item.get("rating"),
        "reviews_count": item.get("reviews"),  # total count
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "place_id": item.get("place_id") or item.get("google_id") or item.get("cid"),
    }

# --- Outscraper: Reviews ---

async def _fetch_reviews_from_outscaper(query: str, reviews_limit: int = 200) -> List[Dict[str, Any]]:
    """
    Calls `maps/reviews-v3` and returns normalized list of review dicts.
    """
    if not OUTSCRAPER_API_KEY:
        raise RuntimeError("OUTSCRAPER_API_KEY is not configured")

    params = {
        "query": query,           # can be place_id or name/address
        "reviewsLimit": reviews_limit,
        "async": "false",
        # Optionally: "sort": "newest", "ignoreEmpty": "true", "language": "en"
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            data = await _request_with_retries(client, "GET", OUTSCRAPER_REVIEWS_URL, params=params)
        except Exception as e:
            logger.error("Outscraper reviews error for query '%s': %s", query, e)
            return []

    # Normalize & pick reviews_data
    places: List[Dict[str, Any]] = []
    if isinstance(data, dict):
        payload = data.get("data") or data.get("items") or data.get("results") or data
        if isinstance(payload, list):
            places = payload[0] if payload and isinstance(payload[0], list) else payload

    all_reviews: List[Dict[str, Any]] = []
    for place in places:
        reviews = place.get("reviews_data") or place.get("reviews") or []
        if not isinstance(reviews, list):
            continue
        for r in reviews:
            created = _parse_review_datetime(r)
            all_reviews.append({
                "author_name": (r.get("author_title") or r.get("author_name") or "Anonymous").strip(),
                "text": _normalized_text(r.get("review_text") or r.get("text") or ""),
                "rating": r.get("review_rating") if r.get("review_rating") is not None else r.get("rating"),
                "created_at": created,
            })
    return all_reviews

# --- Persistence helpers ---

async def _upsert_review(
    session: AsyncSession,
    company: Company,
    author_name: str,
    text: str,
    rating: Optional[int],
    created_at: datetime,
) -> None:
    """
    Insert a review with PostgreSQL UPSERT on review_hash.
    """
    review_hash = generate_review_hash(company.place_id, author_name, text, rating, created_at)

    stmt = insert(Review).values(
        company_id=company.id,
        author_name=author_name.strip() or "Anonymous",
        text=text.strip(),
        rating=int(rating) if rating is not None else None,
        review_hash=review_hash,
        created_at=created_at,
    ).on_conflict_do_nothing(index_elements=["review_hash"])

    await session.execute(stmt)

# --- Public API (requested functions) ---

async def update_company_from_outscaper(company: Company, session: AsyncSession):
    """
    Sync a specific company's details and reviews from Outscraper to PostgreSQL.
    """
    try:
        # 1) Fetch company details (prefer place_id if present; else name/address)
        query_str = company.place_id or company.name
        if company.address:
            query_str = f"{company.name}, {company.address}"

        external = await fetch_company_from_outscaper(query_str)
        if not external:
            logger.warning("No Outscraper company data for: %s", company.name)
            return

        # 2) Update company core fields
        company.address = external.get("full_address") or company.address
        company.phone = external.get("phone") or company.phone
        company.website = external.get("site") or company.website
        if external.get("rating") is not None:
            company.rating = external.get("rating")
        if external.get("reviews_count") is not None:
            company.reviews_count = external.get("reviews_count")
        if external.get("latitude") is not None:
            company.latitude = external.get("latitude")
        if external.get("longitude") is not None:
            company.longitude = external.get("longitude")
        if external.get("place_id") and not company.place_id:
            company.place_id = external.get("place_id")
        company.updated_at = _now_utc()

        await session.flush()

