import logging
import hashlib
import os
from typing import Dict, List, Optional
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

# Import your models from your core models file
# Ensure these match your existing database schema
from app.models import Company, Review 

# Configuration
OUTSCRAPER_API_KEY = os.getenv("OUTSCRAPER_API_KEY")
OUTSCRAPER_URL = "https://api.app.outscraper.com/maps/search-v2"

logger = logging.getLogger(__name__)

def generate_review_hash(author_name: str, text: str, rating: int) -> str:
    """Creates a unique hash for a review to prevent duplicates."""
    raw_str = f"{author_name}|{text}|{rating}"
    return hashlib.md5(raw_str.encode('utf-8')).hexdigest()

async def fetch_company_from_outscaper(query: str) -> List[Dict]:
    """
    Fetches exact business data from Outscraper API.
    Replaces Google Autocomplete/Details logic.
    """
    params = {
        "query": query,
        "limit": 1,  # Adjust if you want to return a list for selection
        "async": "false",
    }
    headers = {"X-API-KEY": OUTSCRAPER_API_KEY}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(OUTSCRAPER_URL, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            # Outscraper returns a list of results inside 'data'
            return data.get("data", [])[0] if data.get("data") else {}
        except Exception as e:
            logger.error(f"Outscraper API error for query '{query}': {e}")
            return {}

async def update_company_from_outscaper(company: Company, session: AsyncSession):
    """
    Syncs a specific company's details and reviews from Outscraper to PostgreSQL.
    """
    try:
        # 1. Fetch fresh data from API
        external_data = await fetch_company_from_outscaper(company.name)
        if not external_data:
            logger.warning(f"No data found for company: {company.name}")
            return

        # 2. Update Company Details
        company.address = external_data.get("full_address", company.address)
        company.phone = external_data.get("phone", company.phone)
        company.website = external_data.get("site", company.website)
        company.rating = external_data.get("rating", company.rating)
        company.reviews_count = external_data.get("reviews_count", company.reviews_count)
        company.latitude = external_data.get("latitude", company.latitude)
        company.longitude = external_data.get("longitude", company.longitude)
        company.updated_at = datetime.utcnow()

        # 3. Sync Reviews
        api_reviews = external_data.get("reviews_data", [])
        for r in api_reviews:
            author = r.get("author_title", "Anonymous")
            text = r.get("review_text", "")
            rating = r.get("review_rating", 0)
            
            await add_review(
                company_id=company.id,
                author_name=author,
                text=text,
                rating=rating,
                session=session
            )

        await session.commit()
        logger.info(f"Successfully synced company and reviews for: {company.name}")

    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to update company {company.id}: {e}")

async def add_review(company_id: int, author_name: str, text: str, rating: int, session: AsyncSession):
    """
    Inserts a review into PostgreSQL if it doesn't already exist (based on hash).
    """
    review_hash = generate_review_hash(author_name, text, rating)
    
    # Use PostgreSQL UPSERT logic to avoid duplicates
    stmt = insert(Review).values(
        company_id=company_id,
        author_name=author_name,
        text=text,
        rating=rating,
        review_hash=review_hash,
        created_at=datetime.utcnow()
    ).on_conflict_do_nothing(index_elements=['review_hash'])
    
    await session.execute(stmt)

async def sync_all_companies_with_outscaper(session: AsyncSession):
    """
    Global sync function: iterates through all active companies and refreshes data.
    """
    logger.info("Starting global Outscraper sync...")
    
    # Fetch all active companies
    result = await session.execute(select(Company).where(Company.is_active == True))
    companies = result.scalars().all()
    
    if not companies:
        logger.info("No active companies found for sync.")
        return

    for company in companies:
        logger.info(f"Syncing: {company.name}")
        await update_company_from_outscaper(company, session)
    
    logger.info("Global sync completed.")

# Helper for the frontend search to replace Google Autocomplete
async def search_and_save_new_business(query: str, session: AsyncSession):
    """
    Logic for when a user searches for a new business on the dashboard.
    """
    business_data = await fetch_company_from_outscaper(query)
    if not business_data:
        return None

    place_id = business_data.get("place_id")
    
    # Check if exists
    stmt = select(Company).where(Company.place_id == place_id)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        await update_company_from_outscaper(existing, session)
        return existing

    # Create new if not exists
    new_company = Company(
        name=business_data.get("name"),
        address=business_data.get("full_address"),
        place_id=place_id,
        phone=business_data.get("phone"),
        website=business_data.get("site"),
        rating=business_data.get("rating"),
        reviews_count=business_data.get("reviews_count"),
        latitude=business_data.get("latitude"),
        longitude=business_data.get("longitude"),
        is_active=True,
        created_at=datetime.utcnow()
    )
    
    session.add(new_company)
    await session.flush() # Get ID
    
    # Sync initial reviews
    await update_company_from_outscaper(new_company, session)
    return new_company
