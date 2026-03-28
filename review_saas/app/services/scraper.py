import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session, relationship, Mapped, mapped_column
from sqlalchemy import Integer, String, ForeignKey, DateTime, func
from serpapi import GoogleSearch

# --- 1. SETUP LOGGING ---
logger = logging.getLogger("app.scraper")
logging.basicConfig(level=logging.INFO)

# --- 2. CONFIGURATION ---
# Your SerpApi Key
SERPAPI_KEY = "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d"

# --- 3. THE MODELS (Required for the logic) ---
# Note: These should match your app/core/models.py
from app.core.db import Base
from app.core.models import Company, CompanyCID

# --- 4. THE CORE LOGIC: RESOLVE AND SAVE ---

def resolve_cid_from_google(place_id: str) -> Optional[str]:
    """
    Calls SerpApi to find the unique CID using a Google Place ID.
    """
    try:
        logger.info(f"🔍 Searching SerpApi for Place ID: {place_id}")
        params = {
            "engine": "google_maps",
            "q": place_id,
            "api_key": SERPAPI_KEY
        }
        search = GoogleSearch(params)
        results = search.get_dict()

        # Extract CID from the 'data_id' field in SerpApi results
        place_results = results.get("place_results", {})
        cid = place_results.get("data_id")

        if not cid:
            # Fallback check if the main result is a list
            local_results = results.get("local_results", [])
            if local_results:
                cid = local_results[0].get("data_id")

        return cid
    except Exception as e:
        logger.error(f"❌ SerpApi API Error: {str(e)}")
        return None

def get_or_fix_company_cid(db: Session, company_id: int) -> Optional[str]:
    """
    The 'Auto-Fix' Function:
    1. Checks if CID exists in the database.
    2. If missing, finds it via Google.
    3. Saves it to the database so you never have to do it manually again.
    """
    # Step A: Look in the company_cids table
    cid_entry = db.query(CompanyCID).filter(CompanyCID.company_id == company_id).first()
    
    if cid_record := cid_entry:
        logger.info(f"✅ CID found in database for Company ID {company_id}: {cid_record.cid}")
        return cid_record.cid

    # Step B: If not found, get the Company details
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company or not company.google_place_id:
        logger.error(f"❌ Error: Company {company_id} has no Google Place ID.")
        return None

    logger.warning(f"⚠️ CID missing for '{company.name}'. Attempting auto-fix...")

    # Step C: Use SerpApi to resolve the ID
    resolved_cid = resolve_cid_from_google(company.google_place_id)

    if resolved_cid:
        try:
            # Step D: Save it permanently to your NEW table
            new_entry = CompanyCID(
                company_id=company.id,
                cid=resolved_cid,
                place_id=company.google_place_id
            )
            db.add(new_entry)
            db.commit()
            logger.info(f"🔥 AUTO-FIX SUCCESS: Saved CID {resolved_cid} for {company.name}")
            return resolved_cid
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Database Save Error: {str(e)}")
            return resolved_cid
    
    logger.error(f"❌ Could not find CID on Google for {company.name}. Please check the Place ID.")
    return None

# --- 5. HOW TO TRIGGER THE INGEST ---

def run_review_ingest(db: Session, company_id: int):
    """
    This is the function you call to start the process.
    """
    # 1. Get/Fix the CID
    cid = get_or_fix_company_cid(db, company_id)

    if not cid:
        logger.error(f"🛑 Ingest Aborted: No CID available for company {company_id}")
        return

    # 2. Use the CID to fetch reviews
    logger.info(f"🚀 Starting Ingest for CID: {cid}")
    
    search_params = {
        "engine": "google_maps_reviews",
        "data_id": cid,
        "api_key": SERPAPI_KEY
    }
    
    # ... Rest of your scraping/saving logic goes here ...
    logger.info("📡 Reviews are now being downloaded...")
