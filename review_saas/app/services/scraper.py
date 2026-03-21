import httpx
import logging
import re
import json
import asyncio
import random
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


async def fetch_reviews(place_id: str, limit: int = 300) -> List[Dict[str, Any]]:
    """
    RAW PROTOBUF SLICER — Hardened & updated for 2026
    Tries multiple pb formats + real browser headers + fallback regex
    """
    all_reviews = []
    collected_ids = set()

    # Rotating headers + referers
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    ]

    pb_formats = [
        "!1s{place_id}!2i0!3i{limit}!4m5!4b1!5b1!6b1!7b1!5e1",
        "!1m1!1s{place_id}!2m2!1i0!2i{limit}!3e1!4m5!4b1!5b1!6b1!7b1!11m1!4b1",
        "!1m1!1s{place_id}!2m2!1i0!2i{limit}!3e1!4m6!4b1!5b1!6b1!7b1!8b1!11m1!4b1",
    ]

    headers_base = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/maps",
        "X-Requested-With": "XMLHttpRequest",
    }

    max_retries = 3
    for attempt in range(max_retries):
        logger.info(f"Protobuf attempt {attempt+1}/{max_retries} for {place_id}")

        headers = headers_base.copy()
        headers["User-Agent"] = random.choice(user_agents)

        async with httpx.AsyncClient(headers=headers, timeout=45.0, follow_redirects=True) as client:
            try:
                # Try different pb formats
                for pb_template in pb_formats:
                    pb = pb_template.format(place_id=place_id, limit=limit)
                    url = f"https://www.google.com/maps/preview/review/listentitiesreviews?pb={pb}"

                    logger.info(f"Trying pb format: {pb[:80]}...")

                    resp = await client.get(url)

                    if resp.status_code != 200:
                        logger.warning(f"HTTP {resp.status_code} on this pb — trying next")
                        await asyncio.sleep(random.uniform(2, 5))
                        continue

                    text = resp.text.strip()

                    # Strip prefix variations
                    prefixes = [")]}'\n", ")]}'\r\n", ")]}'", ")]}"]
                    for p in prefixes:
                        if text.startswith(p):
                            text = text[len(p):].strip()
                            break

                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        logger.warning("JSON parse failed — trying regex fallback")
                        data = None

                    if data and isinstance(data, list) and len(data) > 2 and isinstance(data[2], list):
                        raw_reviews = data[2]
                        added = 0

                        for r in raw_reviews:
                            if len(all_reviews) >= limit:
                                break

                            try:
                                # Safe extraction
                                review_id = str(r[0]) if len(r) > 0 else None
                                if not review_id or review_id in collected_ids:
                                    continue

                                author = "Google User"
                                if len(r) > 0 and isinstance(r[0], list) and len(r[0]) > 1:
                                    author = str(r[0][1]).strip() or author

                                rating = 0
                                if len(r) > 4 and isinstance(r[4], (int, float)):
                                    rating = int(r[4])

                                text = ""
                                if len(r) > 3 and isinstance(r[3], str):
                                    text = r[3].strip()

                                review_time = datetime.now(timezone.utc).isoformat()
                                ts_ms = None
                                if len(r) > 27 and isinstance(r[27], (int, float)):
                                    ts_ms = r[27]
                                if ts_ms and ts_ms > 1000000000000:
                                    review_time = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()

                                all_reviews.append({
                                    "review_id": review_id,
                                    "rating": rating,
                                    "text": text,
                                    "author_name": author,
                                    "google_review_time": review_time,
                                })
                                collected_ids.add(review_id)
                                added += 1

                            except Exception:
                                continue

                        if added > 0:
                            logger.info(f"Success on attempt {attempt+1}: {len(all_reviews)} reviews")
                            return all_reviews[:limit]

                # Regex fallback if all pb formats failed
                logger.info("All pb formats failed — regex slicer activated")
                matches = re.findall(
                    r'\["([a-zA-Z0-9_-]{20,})".*?\[(\d)\].*?"([^"]{10,})"',
                    text,
                    re.DOTALL | re.MULTILINE
                )

                for rid, rating_str, text_part in matches:
                    if len(all_reviews) >= limit:
                        break
                    if rid in collected_ids:
                        continue

                    text_clean = text_part.encode('utf-8').decode('unicode-escape', errors='ignore').strip()
                    all_reviews.append({
                        "review_id": rid,
                        "rating": int(rating_str),
                        "text": text_clean,
                        "author_name": "Extracted User",
                        "google_review_time": datetime.now(timezone.utc).isoformat(),
                    })
                    collected_ids.add(rid)

                if all_reviews:
                    logger.info(f"Regex fallback success: {len(all_reviews)} reviews")
                    return all_reviews[:limit]

                logger.warning(f"Attempt {attempt+1}: No reviews — retrying...")
                await asyncio.sleep(random.uniform(5, 12))

            except Exception as e:
                logger.error(f"Attempt {attempt+1} error: {e}")
                await asyncio.sleep(6)

    logger.error(f"Failed after {max_retries} attempts — 0 reviews")
    return []
