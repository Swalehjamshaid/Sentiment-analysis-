# filename: scraper.py
"""
Google Maps Reviews Scraper (Regional Stealth V4)

- Keeps the same public function: fetch_reviews(place_id: str, limit: int = 1000)
- Adds primary path via Google Search `tbm=map&async=l_rv` (as your logs show)
- Falls back to Maps preview `listentitiesreviews` if the search path yields none
- Robust nested JSON walker to extract reviews from wrapped payloads
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

logger = logging.getLogger(__name__)

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

_GOOGLE_DOMAINS: Tuple[str, ...] = (
    "https://www.google.com.pk",
    "https://www.google.com",
    "https://www.google.com.hk",
)

_JSON_PREFIX = ")]}'\n"
_PER_PAGE = 100
_DEFAULT_TIMEOUT = 30.0
_MAX_PER_HOST_RETRIES = 3
_BACKOFF_BASE_SECONDS = 0.75
_BACKOFF_JITTER = (0.25, 0.75)
_HUMAN_DELAY_RANGE = (0.5, 1.0)

# ----------------------------- URL builders ----------------------------------------

def _build_preview_url(domain: str, place_id: str, offset: int) -> str:
    return (
        f"{domain}/maps/preview/review/listentitiesreviews"
        f"?authuser=0&hl=en&gl=pk&pb=!1s{place_id}!2i{offset}!3i{_PER_PAGE}!4m5!4b1!5b1!6b1!7b1!5e1"
    )

def _build_search_url(domain: str, place_id: str) -> str:
    # Mirrors what your logs show (tbm=map async=l_rv...l_rid:<place_id>)
    q = f"reviews for place_id:{place_id}"
    # Properly encode only the value, not the whole query string
    q_encoded = httpx.QueryParams({"q": q})["q"]
    return (
        f"{domain}/search?q={q_encoded}&tbm=map"
        f"&async=l_rv:1,l_rid:{place_id},l_oc:0,_fmt:json"
    )

# ----------------------------- helpers ---------------------------------------------

def _strip_xssi_prefix(text: str) -> str:
    if text.startswith(_JSON_PREFIX):
        return text[len(_JSON_PREFIX):]
    if text.startswith(")]}'"):
        return text[4:]
    return text

def _safe_get_timestamp_ms(r: Sequence[Any]) -> Optional[int]:
    for idx in (27, 18, 19):
        try:
            ts = r[idx]
            if isinstance(ts, (int, float)):
                return int(ts)
        except Exception:
            continue
    return None

def _parse_review(r: Sequence[Any]) -> Optional[Dict[str, Any]]:
    try:
        review_id = str(r[0]) if r and r[0] is not None else None
        rating = int(r[4]) if len(r) > 4 and r[4] is not None else None
        text = str(r[3]) if len(r) > 3 and r[3] else ""

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
            if ts_ms else None
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

def _walk_and_collect(node: Any, out: List[Dict[str, Any]], limit: int) -> None:
    """
    Depth-first walk over nested lists/dicts to fish out review tuples
    that parse via _parse_review.
    """
    if len(out) >= limit:
        return

    if isinstance(node, list):
        parsed = _parse_review(node)
        if parsed:
            out.append(parsed)
            if len(out) >= limit:
                return
        for item in node:
            _walk_and_collect(item, out, limit)
    elif isinstance(node, dict):
        for v in node.values():
            _walk_and_collect(v, out, limit)

async def _get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_retries: int = _MAX_PER_HOST_RETRIES,
) -> Optional[httpx.Response]:
    attempt = 0
    last_exc: Optional[BaseException] = None
    while attempt <= max_retries:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp
            logger.warning("🕵️ HTTP status %s on attempt %s for %s", resp.status_code, attempt, url)
        except Exception as e:
            last_exc = e
            logger.warning("🕵️ Network exception on attempt %s for %s: %s", attempt, url, e)
        if attempt < max_retries:
            backoff = _BACKOFF_BASE_SECONDS * (2 ** attempt) + random.uniform(*_BACKOFF_JITTER)
            await asyncio.sleep(backoff)
        attempt += 1
    if last_exc:
        logger.error("🕵️ Exhausted retries; last error: %s", last_exc)
    return None

# ----------------------------- main API --------------------------------------------

async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Try Google Search async endpoint first; fall back to Maps preview.
    Returns a list of dicts: review_id, rating, text, author, timestamp_ms, date
    """
    all_reviews: List[Dict[str, Any]] = []

    timeout = httpx.Timeout(_DEFAULT_TIMEOUT)
    headers = dict(_MOBILE_HEADERS_BASE)

    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        # 1) Search async path
        for domain in _GOOGLE_DOMAINS:
            url = _build_search_url(domain, place_id)
            resp = await _get_with_retries(client, url)
            if not resp:
                continue
            try:
                raw = _strip_xssi_prefix(resp.text)
                outer = json.loads(raw)
            except Exception:
                continue

            # The payload usually embeds inner JSON strings (e.g., ["wrb.fr", null, "<JSON>"])
            candidates: List[Any] = []
            def _scan(o: Any):
                if isinstance(o, list):
                    for it in o:
                        _scan(it)
                elif isinstance(o, str):
                    s = o.strip()
                    if s.startswith("[") or s.startswith("{"):
                        try:
                            candidates.append(json.loads(s))
                        except Exception:
                            pass
                elif isinstance(o, dict):
                    for v in o.values():
                        _scan(v)
            _scan(outer)

            page_items: List[Dict[str, Any]] = []
            for c in candidates:
                _walk_and_collect(c, page_items, limit)
                if len(page_items) >= limit:
                    break

            if page_items:
                take = min(len(page_items), max(0, limit - len(all_reviews)))
                all_reviews.extend(page_items[:take])
                logger.info("🟢 Search endpoint yielded %s reviews", take)
                if len(all_reviews) >= limit:
                    return all_reviews
                await asyncio.sleep(random.uniform(*_HUMAN_DELAY_RANGE))
                break  # stop trying other domains since we got results

        # 2) Fallback: maps preview paginated
        offset = 0
        while len(all_reviews) < limit:
            response = None
            last_url = None
            for domain in _GOOGLE_DOMAINS:
                url = _build_preview_url(domain, place_id, offset)
                last_url = url
                response = await _get_with_retries(client, url)
                if response is not None:
                    break
            if response is None:
                logger.error("🕵️ Regional wall at offset %s; last URL: %s", offset, last_url)
                break
            try:
                raw_text = _strip_xssi_prefix(response.text)
                data = json.loads(raw_text)
            except Exception as e:
                logger.error("🕵️ JSON parse failure at offset %s: %s", offset, e)
                break

            batch = None
            try:
                batch = data[2] if len(data) > 2 else None
            except Exception:
                batch = None

            if not batch:
                logger.info("✅ Reached end of stream at offset %s", offset)
                break

            added = 0
            for r in batch:
                if len(all_reviews) >= limit:
                    break
                parsed = _parse_review(r)
                if parsed:
                    all_reviews.append(parsed)
                    added += 1
            if added == 0:
                logger.info("✅ No more parsable reviews at offset %s — stopping.", offset)
                break
            offset += _PER_PAGE
            await asyncio.sleep(random.uniform(*_HUMAN_DELAY_RANGE))

    return all_reviews

__all__ = ["fetch_reviews"]
