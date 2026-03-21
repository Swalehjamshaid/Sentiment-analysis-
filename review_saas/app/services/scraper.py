# filename: scraper.py
"""
Google Maps Reviews Scraper (Regional Stealth V3)

⚠️ Note:
- This module is designed to keep your existing project alignment intact.
- It exposes **fetch_reviews(place_id: str, limit: int = 1000)** exactly as used by
  your routes (e.g., app/routes/reviews.py) so imports remain unchanged.
- It uses a Pakistan (.com.pk) mobile web endpoint first and includes resilient
  fallbacks, structured parsing, and cautious delays.
- While hardened against transient errors, network or upstream changes can still
  affect reliability—no scraper can guarantee 100% success against third‑party
  rate limits or markup/index changes.

Usage example (manual test):
  $ PLACE_ID=ChIJN1t_tDeuEmsRUsoyG83frY4 python -m scraper

Environment:
- Requires: httpx, asyncio
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

# This logger helps you see the "Spy" progress in Railway logs
logger = logging.getLogger(__name__)

# --- Configuration -----------------------------------------------------------------
_MOBILE_HEADERS_BASE: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-PK,en;q=0.9",
    "Referer": "https://www.google.com.pk/",
    "X-Requested-With": "XMLHttpRequest",
}

# Primary domain first (.com.pk), then generic fallbacks.
_GOOGLE_DOMAINS: Tuple[str, ...] = (
    "https://www.google.com.pk",
    "https://www.google.com",
    "https://www.google.com.hk",  # extra fallback often stable for maps preview
)

_JSON_PREFIX = ")]}'\n"
_PER_PAGE = 100  # number of reviews requested per page (Google "3i100")
_DEFAULT_TIMEOUT = 30.0
_MAX_PER_HOST_RETRIES = 3
_BACKOFF_BASE_SECONDS = 0.75
_BACKOFF_JITTER = (0.25, 0.75)
_HUMAN_DELAY_RANGE = (0.5, 1.0)  # delay between successful page requests

# ------------------------------------------------------------------------------------

def _build_url(domain: str, place_id: str, offset: int) -> str:
    # Endpoint observed for Google Maps web preview reviews (mobile-ish path)
    return (
        f"{domain}/maps/preview/review/listentitiesreviews"
        f"?authuser=0&hl=en&gl=pk&pb=!1s{place_id}!2i{offset}!3i{_PER_PAGE}!4m5!4b1!5b1!6b1!7b1!5e1"
    )


def _strip_xssi_prefix(text: str) -> str:
    # Google often wraps JSON with an XSSI protection prefix ")]}'\n"
    if text.startswith(_JSON_PREFIX):
        return text[len(_JSON_PREFIX) :]
    # Some variants may have just the ")]}'" without newline
    if text.startswith(")]}'"):
        return text[4:]
    return text


def _safe_get_timestamp_ms(r: Sequence[Any]) -> Optional[int]:
    # Primary index observed is 27; some variants have timestamp in other slots.
    for idx in (27, 18, 19):
        try:
            ts = r[idx]
            if isinstance(ts, (int, float)):
                return int(ts)
        except Exception:
            continue
    return None


def _parse_review(r: Sequence[Any]) -> Optional[Dict[str, Any]]:
    """Parse a single raw review record from the preview payload.

    The structure is sparsely documented and may shift; we guard with try/except
    and best-effort indexing.
    """
    try:
        review_id = str(r[0]) if r and r[0] is not None else None
        rating = int(r[4]) if len(r) > 4 and r[4] is not None else None
        text = str(r[3]) if len(r) > 3 and r[3] else ""

        # Author name path observed: r[1][4][0][4]
        author = "Local User"
        if len(r) > 1 and isinstance(r[1], list):
            try:
                author_candidate = r[1][4][0][4]
                if author_candidate:
                    author = str(author_candidate)
            except Exception:
                pass

        ts_ms = _safe_get_timestamp_ms(r)
        date_iso = (
            datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
            if ts_ms
            else None
        )

        if review_id is None or rating is None:
            return None

        return {
            "review_id": review_id,
            "rating": rating,
            "text": text,
            "author": author,
            "timestamp_ms": ts_ms,
            "date": date_iso,
        }
    except Exception:
        return None


async def _get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_retries: int = _MAX_PER_HOST_RETRIES,
) -> Optional[httpx.Response]:
    """GET with bounded retries + exponential backoff and jitter."""
    attempt = 0
    last_exc: Optional[BaseException] = None

    while attempt <= max_retries:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp

            # For non-200, we treat as retryable up to max_retries
            logger.warning(
                "\U0001F575\uFE0F Regional/HTTP issue (status %s) on attempt %s for %s",
                resp.status_code,
                attempt,
                url,
            )
        except Exception as e:  # network/timeout
            last_exc = e
            logger.warning(
                "\U0001F575\uFE0F Network exception on attempt %s for %s: %s",
                attempt,
                url,
                e,
            )

        # backoff before next try
        if attempt < max_retries:
            backoff = _BACKOFF_BASE_SECONDS * (2 ** attempt)
            jitter = random.uniform(*_BACKOFF_JITTER)
            await asyncio.sleep(backoff + jitter)
        attempt += 1

    if last_exc:
        logger.error("\U0001F575\uFE0F Exhausted retries; last error: %s", last_exc)
    return None


async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    REGIONAL STEALTH V3

    Aligned function name to match existing imports in app/routes/reviews.py.
    Uses the .com.pk domain first to reduce regional 400 errors, with smart
    domain fallbacks, resilient parsing, and human-like pacing.

    Args:
        place_id: Google Maps Place ID (e.g., ChIJN1t_tDeuEmsRUsoyG83frY4)
        limit: Maximum number of reviews to collect.

    Returns:
        A list of reviews as dicts with keys: review_id, rating, text, author,
        timestamp_ms, date (ISO-8601 in UTC).
    """
    all_reviews: List[Dict[str, Any]] = []
    offset = 0

    headers = dict(_MOBILE_HEADERS_BASE)

    timeout = httpx.Timeout(_DEFAULT_TIMEOUT)
    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        while len(all_reviews) < limit:
            # Try each domain in order for this page of results
            response: Optional[httpx.Response] = None
            last_url: Optional[str] = None

            for domain in _GOOGLE_DOMAINS:
                url = _build_url(domain, place_id, offset)
                last_url = url
                response = await _get_with_retries(client, url)
                if response is not None:
                    break  # we got a 200 OK

            if response is None:
                logger.error(
                    "\U0001F575\uFE0F Regional wall hit at offset %s; last tried URL: %s",
                    offset,
                    last_url,
                )
                break

            # Parse JSON payload (strip XSSI prefix first)
            try:
                raw_text = _strip_xssi_prefix(response.text)
                data = json.loads(raw_text)
            except Exception as e:
                logger.error("\U0001F575\uFE0F JSON parse failure at offset %s: %s", offset, e)
                break

            # Expected structure: data[2] holds the list of reviews
            try:
                batch = data[2] if len(data) > 2 else None
            except Exception:
                batch = None

            if not batch:
                logger.info("✅ Collection finished at offset %s", offset)
                break

            added_this_page = 0
            for r in batch:
                if len(all_reviews) >= limit:
                    break
                parsed = _parse_review(r)
                if parsed is not None:
                    all_reviews.append(parsed)
                    added_this_page += 1

            # If nothing parsed from this page, likely end of results or structure changed
            if added_this_page == 0:
                logger.info("✅ No more parsable reviews at offset %s — stopping.", offset)
                break

            offset += _PER_PAGE

            # Human-like pacing to reduce flagging risk
            await asyncio.sleep(random.uniform(*_HUMAN_DELAY_RANGE))

    return all_reviews


__all__ = ["fetch_reviews"]


# --- Manual test runner -------------------------------------------------------------
if __name__ == "__main__":
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    place_id = os.getenv("PLACE_ID")
    if not place_id:
        logger.error("Please export PLACE_ID environment variable to run the demo.")
        raise SystemExit(2)

    async def _demo() -> None:
        reviews = await fetch_reviews(place_id, limit=200)
        print(json.dumps({"count": len(reviews), "sample": reviews[:2]}, ensure_ascii=False, indent=2))

    asyncio.run(_demo())
