# filename: app/services/scraper.py
from __future__ import annotations
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.core.models import CompanyCID, Company, Review
from app.services.external_api import fetch_google_reviews  # your Playwright / API scraper

logger = logging.getLogger("app.scraper")


# ---------------------------
# Fetch Reviews with CID Support
# ---------------------------
async def fetch_reviews(
    place_id: str,
    session: AsyncSession,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Fetches reviews from Google for a company using CID stored in DB.
    If CID exists, uses it; otherwise scrapes the CID and saves it.
    """
    # 1️⃣ Check if CID exists in DB
    result = await session.execute(
        select(CompanyCID).join(Company).where(Company.google_place_id == place_id)
    )
    cid_record: Optional[CompanyCID] = result.scalar_one_or_none()

    if cid_record:
        cid = cid_record.cid
        logger.info(f"✅ Using stored CID for place_id {place_id}: {cid}")
    else:
        # Fetch CID via external API / Playwright scraper
        cid = await get_cid_from_place(place_id)
        if not cid:
            logger.warning(f"⚠️ Could not resolve CID for place_id {place_id}")
            return []

        # Save CID to DB
        new_cid = CompanyCID(
            cid=cid,
            company_id=(await get_company_id_by_place_id(place_id, session))
        )
        session.add(new_cid)
        await session.commit()
        logger.info(f"✅ Stored new CID for place_id {place_id}: {cid}")

    # 2️⃣ Fetch reviews using CID
    reviews_data = await fetch_google_reviews(cid=cid, limit=limit)
    return reviews_data


# ---------------------------
# Helper: Get CID via external source
# ---------------------------
async def get_cid_from_place(place_id: str) -> Optional[str]:
    """
    Placeholder for logic to fetch CID via Google Place URL or Playwright API.
    Replace this with your actual scraping logic.
    """
    # Example: call your Playwright / SERP API function
    try:
        cid = await some_playwright_scraper(place_id)  # implement this
        return cid
    except Exception as e:
        logger.error(f"Error fetching CID for {place_id}: {e}")
        return None


# ---------------------------
# Helper: Get Company ID from place_id
# ---------------------------
async def get_company_id_by_place_id(place_id: str, session: AsyncSession) -> Optional[int]:
    result = await session.execute(
        select(Company.id).where(Company.google_place_id == place_id)
    )
    company_id: Optional[int] = result.scalar_one_or_none()
    if not company_id:
        logger.warning(f"Company not found for place_id {place_id}")
    return company_id
