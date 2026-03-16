# filename: app/services/review.py

from __future__ import annotations

import os
import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import Company, Review

# -------------------------------
# Logging
# -------------------------------
logger = logging.getLogger("review_service")
logger.setLevel(logging.INFO)

# -------------------------------
# Google API Config
# -------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
GOOGLE_PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
GOOGLE_PLACE_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"

# -------------------------------
# Fetch Google Place ID
# -------------------------------
async def fetch_google_place_id(company_name: str, address: str) -> Optional[str]:
    """Fetch Google Place ID for a company using name and address."""
    params = {
        "input": f"{company_name} {address}",
        "inputtype": "textquery",
        "fields": "place_id",
        "key": GOOGLE_API_KEY,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(GOOGLE_PLACE_SEARCH_URL, params=params)
        if resp.status_code != 200:
            logger.error(f"Google Place Search failed: {resp.text}")
            return None
        data = resp.json()
        candidates = data.get("candidates")
        if not candidates:
            return None
        return candidates[0].get("place_id")

# -------------------------------
# Fetch Google Place Details
# -------------------------------
async def fetch_google_place_details(place_id: str) -> Optional[Dict[str, Any]]:
    """Fetch detailed information of a company from Google Places API."""
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,geometry,formatted_phone_number,website,rating,user_ratings_total",
        "key": GOOGLE_API_KEY,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(GOOGLE_PLACE_DETAILS_URL, params=params)
        if resp.status_code != 200:
            logger.error(f"Google Place Details failed: {resp.text}")
            return None
        result = resp.json().get("result")
        return result

# -------------------------------
# Update Company from Google
# -------------------------------
async def update_company_from_google(company: Company, session: AsyncSession) -> None:
    """Fetch Google data for a company and update DB."""
    try:
        place_id = await fetch_google_place_id(company.name, company.address)
        if not place_id:
            logger.warning(f"No Google Place ID found for {company.name}")
            return

        details = await fetch_google_place_details(place_id)
        if not details:
            logger.warning(f"No details returned for Place ID {place_id}")
            return

        company.google_place_id = place_id
        company.latitude = details.get("geometry", {}).get("location", {}).get("lat")
        company.longitude = details.get("geometry", {}).get("location", {}).get("lng")
        company.phone = details.get("formatted_phone_number")
        company.website = details.get("website")
        company.rating = details.get("rating")
        company.reviews_count = details.get("user_ratings_total", 0)
        company.is_active = True

        session.add(company)
        await session.commit()
        logger.info(f"Updated company {company.name} with Google data.")
    except Exception as e:
        logger.error(f"Error updating company {company.name}: {e}")

# -------------------------------
# Add Review
# -------------------------------
async def add_review(company_id: int, author_name: str, text: str, rating: float, session: AsyncSession) -> Review:
    """Add a new review to the database."""
    review_hash = hashlib.sha256(f"{company_id}{author_name}{text}{datetime.utcnow()}".encode()).hexdigest()
    review = Review(
        company_id=company_id,
        author_name=author_name,
        text=text,
        rating=rating,
        review_hash=review_hash,
        created_at=datetime.utcnow(),
    )
    session.add(review)
    await session.commit()
    logger.info(f"Added review for company_id {company_id}")
    return review

# -------------------------------
# Sync all Companies with Google
# -------------------------------
async def sync_all_companies_with_google() -> None:
    """Update all inactive companies in the database with Google data."""
    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.is_active == False))
        companies: List[Company] = result.scalars().all()
        for company in companies:
            await update_company_from_google(company, session)
        logger.info("Finished syncing all companies.")
