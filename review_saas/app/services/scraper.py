import os
import logging
from typing import List, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from serpapi import GoogleSearch
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger("app.scraper")


def _serpapi_call(params: dict) -> dict:
    """
    Blocking SerpApi call – always executed inside a threadpool.
    """
    search = GoogleSearch(params)
    return search.get_dict()


async def fetch_reviews(
    place_id: Optional[str] = None,
    company_id: Optional[int] = None,
    limit: int = 300,
    name: Optional[str] = None,
    session: AsyncSession = None
) -> List[Dict]:
    """
    Fetch Google reviews using CID from company_cids table only.
    """
    analyzer = SentimentIntensityAnalyzer()

    api_key = os.getenv("SERP_API_KEY")
    if not api_key:
        logger.error("❌ SERP_API_KEY environment variable is not set!")
        return []

    cid = None
    target_name = (name or "Unknown Business").strip()

    # 1️⃣ Lookup CID from Database
    if company_id and session:
        try:
            from app.core.models import CompanyCID

            logger.info(
                f"📋 Looking up CID for company_id={company_id} | Name: {target_name}"
            )

            result = await session.execute(
                select(CompanyCID).where(
                    CompanyCID.company_id == company_id
                )
            )
            db_entry = result.scalar_one_or_none()

            if db_entry and db_entry.cid:
                cid = db_entry.cid
                logger.info(f"✅ CID successfully loaded from database: {cid}")
            else:
                logger.warning(
                    f"⚠️ No CID found in company_cids table for "
                    f"company_id {company_id} ({target_name})"
                )

        except Exception as e:
            logger.error(
                f"❌ Failed to read CompanyCID table: {e}",
                exc_info=True
            )
    else:
        logger.error("❌ company_id or database session is missing.")

    # ❗ Hard stop if no CID
    if not cid:
        logger.error(
            f"❌ No CID available in database for '{target_name}'. "
            f"Please insert CID into company_cids table first."
        )
        return []

    # 2️⃣ Call SerpApi (only if CID exists)
    try:
        logger.info(f"📍 Calling SerpApi with CID: {cid} for {target_name}")

        collected: List[Dict] = []
        seen_ids = set()
        next_page_token = None

        while len(collected) < limit:
            params = {
                "engine": "google_maps_reviews",
                "data_id": cid,
                "api_key": api_key,
                "hl": "en",
                "no_cache": True,
                "num": min(100, limit - len(collected)),
                "sort_by": "newestFirst",
            }

            if next_page_token:
                params["next_page_token"] = next_page_token

            results = await run_in_threadpool(
                _serpapi_call,
                params
            )

            raw_reviews = results.get("reviews", [])
            next_page_token = (
                results.get("serpapi_pagination", {})
                .get("next_page_token")
            )

            if not raw_reviews:
                logger.warning("⚠️ No more reviews returned by SerpApi.")
                break

            for r in raw_reviews:
                review_id = r.get("review_id") or r.get("data_id")
                if not review_id or review_id in seen_ids:
                    continue

                seen_ids.add(review_id)

                body = (
                    r.get("snippet")
                    or r.get("text")
                    or r.get("content")
                    or "No comment"
                )

                vs = analyzer.polarity_scores(body)

                if vs["compound"] >= 0.05:
                    sentiment = "Positive"
                elif vs["compound"] <= -0.05:
                    sentiment = "Negative"
                else:
                    sentiment = "Neutral"

                collected.append({
                    "review_id": review_id,
                    "author_name": r.get("user", {}).get("name", "Anonymous"),
                    "rating": r.get("rating", 0),
                    "text": body,
                    "sentiment": sentiment,
                })

            if not next_page_token:
                break

        logger.info(
            f"✅ Successfully captured {len(collected)} reviews "
            f"for '{target_name}'."
        )
        return collected

    except Exception as e:
        logger.error(
            f"❌ SerpApi call failed for CID {cid}: {e}",
            exc_info=True
        )
        return []
