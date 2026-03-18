# filename: app/services/scraper.py

import asyncio
import httpx
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

GOOGLE_REVIEWS_URL = "https://www.google.com/maps/preview/review/listentitiesreviews"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
    ),
    "Referer": "https://www.google.com/",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

DEFAULT_PARAMS_BASE = {
    "authuser": "0",
    "hl": "en",
    "gl": "us",
}

def _strip_xssi_prefix(text: str) -> str:
    if text.startswith(")]}'"):
        return text[4:].lstrip()
    return text

def _safe_from_timestamp_ms(ts_ms: Optional[int]) -> str:
    try:
        if ts_ms:
            return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
    except Exception:
        pass
    return datetime.now(tz=timezone.utc).isoformat()

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default

def _extract_author_name(raw: Any) -> str:
    if isinstance(raw, list):
        # Try [0][1]
        try:
            if isinstance(raw[0], list) and isinstance(raw[0][1], str) and raw[0][1].strip():
                return raw[0][1].strip()
        except Exception:
            pass
        # Try [1][1]
        try:
            if isinstance(raw[1], list) and isinstance(raw[1][1], str) and raw[1][1].strip():
                return raw[1][1].strip()
        except Exception:
            pass
        for item in raw:
            if isinstance(item, list) and len(item) > 1 and isinstance(item[1], str) and item[1].strip():
                return item[1].strip()
    return "Google User"

def _extract_review_id(raw: Any) -> str:
    if isinstance(raw, list):
        try:
            if isinstance(raw[0], str) and raw[0].strip():
                return str(raw[0]).strip()
        except Exception:
            pass
        try:
            if isinstance(raw[0], list) and raw[0] and isinstance(raw[0][0], (str, int)):
                return str(raw[0][0]).strip()
        except Exception:
            pass
        try:
            if isinstance(raw[1], list) and raw[1] and isinstance(raw[1][0], (str, int)):
                return str(raw[1][0]).strip()
        except Exception:
            pass
    return str(raw)[:64]

def _extract_text(raw: Any) -> str:
    try:
        if isinstance(raw, list) and len(raw) > 3:
            val = raw[3]
            if isinstance(val, str):
                return val
            if isinstance(val, list):
                parts = [x for x in val if isinstance(x, str)]
                if parts:
                    return " ".join(parts)
    except Exception:
        pass
    return ""

def _extract_rating(raw: Any) -> int:
    try:
        if isinstance(raw, list) and len(raw) > 4:
            return _safe_int(raw[4], default=0)
    except Exception:
        pass
    return 0

def _extract_time_ms_slot(raw: Any) -> Optional[int]:
    if not isinstance(raw, list):
        return None
    likely_indices = (27, 25, 22, 21, 20, 18, 12)
    for idx in likely_indices:
        try:
            if len(raw) > idx and isinstance(raw[idx], (int, float)) and raw[idx] > 0:
                return int(raw[idx])
        except Exception:
            continue
    return None

async def _http_get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    params: Dict[str, Any],
    max_attempts: int = 3,
    base_delay: float = 0.6,
) -> httpx.Response:
    attempt = 0
    last_exc: Optional[Exception] = None
    while attempt < max_attempts:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp
        except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            last_exc = e
            attempt += 1
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(f"HTTP timeout on attempt {attempt}/{max_attempts}; backing off {delay:.2f}s")
            await asyncio.sleep(delay)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            if status in (429, 500, 502, 503, 504):
                last_exc = e
                attempt += 1
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(f"HTTP {status} on attempt {attempt}/{max_attempts}; backing off {delay:.2f}s")
                await asyncio.sleep(delay)
            else:
                raise
        except Exception as e:
            last_exc = e
            break
    if last_exc:
        raise last_exc
    raise RuntimeError("Unknown HTTP retry failure")

async def fetch_reviews(place_id: str, limit: int = 300, skip: int = 0) -> List[Dict[str, Any]]:
    """
    High-speed Google Review extraction with pagination support.
    :param place_id: Google Place ID
    :param limit: Number of records to fetch
    :param skip: The starting index (offset) for the fetch.
    :return: List of dicts with keys: review_id, rating, text, author_name, google_review_time
    """
    pb = f"!1m1!1s{place_id}!2m2!1i{skip}!2i{limit}!3e1!4m5!4b1!5b1!6b1!7b1!11m1!4b1"
    params = {**DEFAULT_PARAMS_BASE, "pb": pb}
    reviews_list: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=30.0, http2=True) as client:
        try:
            response = await _http_get_with_retries(client, GOOGLE_REVIEWS_URL, params=params)
            content = _strip_xssi_prefix(response.text)
            data = json.loads(content)

            if not isinstance(data, list) or len(data) < 3:
                logger.warning("Unexpected Google reviews payload shape (root)")
                return []

            raw_reviews = data[2] if len(data) > 2 else None
            if not isinstance(raw_reviews, list):
                logger.warning("Unexpected Google reviews payload shape (data[2])")
                return []

            for r in raw_reviews:
                try:
                    review_id = _extract_review_id(r)
                    rating = _extract_rating(r)
                    text = _extract_text(r)
                    author_name = _extract_author_name(r)
                    ts_ms = _extract_time_ms_slot(r)
                    google_review_time = _safe_from_timestamp_ms(ts_ms)

                    reviews_list.append(
                        {
                            "review_id": str(review_id),
                            "rating": int(rating),
                            "text": text or "",
                            "author_name": author_name or "Google User",
                            "google_review_time": google_review_time,
                        }
                    )
                except Exception as inner_e:
                    logger.debug(f"Failed to parse a review entry: {inner_e}")
                    continue

        except Exception as e:
            logger.error(f"Scraper Pagination Error for {place_id} at offset {skip}: {e}")
            return []

    return reviews_list
