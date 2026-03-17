import asyncio
import logging
import httpx
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.models import Company

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def get_google_id_from_place_id(place_id: str) -> str:
    """
    Converts a standard Google Place ID into the hex-based Google ID (Feature ID)
    required by the Fast Scraper.
    """
    # This uses a public Google endpoint to find the internal ID mapping
    url = f"https://www.google.com/maps/search/?api=1&query=google&query_place_id={place_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        try:
            response = await client.get(url)
            # We search the response HTML for the 0x format
            import re
            match = re.search(r'0x[0-9a-fA-F]+:0x[0-9a-fA-F]+', response.text)
            if match:
                return match.group(0)
        except Exception as e:
            logger.error(f"Failed to resolve ID for {place_id}: {e}")
    
    return None

async def run_fix():
    """
    Scans the database for companies missing a google_id and fixes them.
    """
    async for session in get_session():
        # 1. Find all companies where google_id is NULL or empty
        stmt = select(Company).where(
            (Company.google_id == None) | (Company.google_id == "")
        )
        result = await session.execute(stmt)
        companies = result.scalars().all()

        if not companies:
            logger.info("✅ All companies already have valid Google IDs.")
            return

        logger.info(f"🔍 Found {len(companies)} companies needing ID repair.")

        for company in companies:
            # We use the place_id (which your modal already saves) to find the google_id
            if not company.place_id:
                logger.warning(f"⚠️ Company '{company.name}' is missing both IDs. Skipping.")
                continue

            new_id = await get_google_id_from_place_id(company.place_id)
            
            if new_id:
                company.google_id = new_id
                logger.info(f"✅ Fixed {company.name}: {new_id}")
            else:
                logger.error(f"❌ Could not find Google ID for {company.name}")

        # 2. Save changes to database
        try:
            await session.commit()
            logger.info("🚀 Database Patch Complete.")
        except Exception as e:
            await session.rollback()
            logger.error(f"Database commit failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_fix())
