import asyncio
import httpx
import re
import logging
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Company

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def resolve_google_id(place_id: str):
    """Finds the 0x identifier using the public Google Maps redirector."""
    url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        try:
            response = await client.get(url)
            # Search for the hex pattern 0x...:0x...
            match = re.search(r'0x[0-9a-fA-F]+:0x[0-9a-fA-F]+', response.text)
            return match.group(0) if match else None
        except Exception as e:
            logger.error(f"Error resolving {place_id}: {e}")
            return None

async def main():
    async for session in get_session():
        # Find companies missing the google_id
        stmt = select(Company).where(Company.google_id == None)
        result = await session.execute(stmt)
        companies = result.scalars().all()

        if not companies:
            print("✅ All companies already have Google IDs!")
            return

        print(f"🔍 Found {len(companies)} companies to fix...")

        for company in companies:
            print(f"Attempting fix for: {company.name}")
            new_id = await resolve_google_id(company.place_id)
            if new_id:
                company.google_id = new_id
                print(f"✨ Found ID: {new_id}")
            else:
                print(f"❌ Could not find ID for {company.name}")

        await session.commit()
        print("🚀 Database updated successfully!")

if __name__ == "__main__":
    asyncio.run(main())
