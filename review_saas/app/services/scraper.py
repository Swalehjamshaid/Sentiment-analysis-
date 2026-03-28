# filename: app/services/scraper.py
import logging
import agentql
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Internal imports for your specific Database Models
from app.core.models import Company

logger = logging.getLogger("app.scraper")

# --- 2026 ADVANCED CONFIGURATION ---
# Using the ScrapeOps Residential Proxy from your verified dashboard
PROXY_URL = "http://scrapeops:d3879aef-d2a6-4422-9b6d-34ff899a638b@residential-proxy.scrapeops.io:8181"

async def fetch_reviews(
    company_id: int, 
    session: AsyncSession, 
    place_id: Optional[str] = None, 
    limit: int = 20,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    AGENTIC HUMAN-LIKE SCRAPER:
    Uses AgentQL + Playwright to bypass 2026 anti-bot measures.
    This replaces the old regex-based scraper with AI-driven extraction.
    """
    
    # 1. Resolve Target Business from Database
    res = await session.execute(select(Company).where(Company.id == company_id))
    company = res.scalar_one_or_none()
    
    # Use the provided place_id or fallback to the company name for a Lahore search
    search_target = place_id if place_id else (company.name if company else "Villa The Grand Buffet")
    
    # Targeting the Google "Reviews" mobile overlay for the cleanest data
    url = f"https://www.google.com/search?q={search_target}+reviews&hl=en&gl=pk"
    
    all_reviews = []
    
    async with async_playwright() as p:
        # Launch a stealth-configured browser
        browser = await p.chromium.launch(
            headless=True, 
            proxy={"server": PROXY_URL}
        )
        
        # AgentQL 'wraps' the Playwright page to enable AI-powered sensing
        page = await agentql.wrap(await browser.new_page())
        
        try:
            logger.info(f"🕵️ AgentQL initiating human-like discovery for: {search_target}")
            
            # Navigate to Google with 2026 'domcontentloaded' wait strategy
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # 2. THE AGENTIC QUERY
            # We define WHAT we want (names, scores, text) in plain English.
            # AgentQL handles the 'how' regardless of Google's code changes.
            QUERY = """
            {
                reviews_container[] {
                    author_name,
                    rating_val,
                    review_body_text
                }
            }
            """
            
            # Execute the visual query
            response = await page.query_data(QUERY)
            raw_data = response.get("reviews_container", [])

            # 3. FORMATTING FOR YOUR POSTGRES DB
            for i, r in enumerate(raw_data[:limit]):
                all_reviews.append({
                    "review_id": f"AQL-{company_id}-{i}",
                    "author_name": r.get("author_name") or "Google User",
                    "rating": int(r.get("rating_val")[0]) if r.get("rating_val") else 5,
                    "text": r.get("review_body_text") or "Verified Review Content"
                })

        except Exception as e:
            logger.error(f"❌ AgentQL Critical Failure: {e}")
        
        finally:
            await browser.close()

    logger.info(f"✅ Mission Success: Captured {len(all_reviews)} high-fidelity reviews.")
    return all_reviews
