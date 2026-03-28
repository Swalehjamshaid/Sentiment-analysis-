# filename: app/services/scraper_service.py
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from serpapi import GoogleSearch

# Import your shared Base and Models
from app.core.db import Base, engine
from app.core.models import Company, CompanyCID, Review

# --- 1. SETUP LOGGING ---
logger = logging.getLogger("app.scraper")
logging.basicConfig(level=logging.INFO)

# --- 2. CONFIGURATION ---
# Your verified SerpApi Key
SERPAPI_KEY = "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d"

# --- 3. CID RESOLUTION LOGIC (The "Fixer") ---

def resolve_cid_from_google(place_id: str) -> Optional[str]:
    """
    Calls SerpApi to find the unique CID (data_id) using a Google Place ID.
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

        # Try to extract CID from 'place_results'
        place_results = results.get("place_results", {})
        cid = place_results.get("data_id")

        # Fallback: Check 'local_results' if place_results is empty
        if not cid:
            local_results = results.get("local_results", [])
            if local_results:
                cid = local_results[0].get("data_id")
        
        return cid
    except Exception as e:
        logger.error(f"❌ SerpApi API Error during resolution: {str(e)}")
        return None

def get_or_fix_company_cid(db: Session, company_id: int) -> Optional[str]:
    """
    Checks DB for CID. If missing, finds it via API and SAVES it to DB.
    """
    # Step 1: Check the company_cids table
    cid_record = db.query(CompanyCID).filter(CompanyCID.company_id == company_id).first()
    
    if cid_record:
        return cid_record.cid

    # Step 2: If missing, get the Company's Google Place ID
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company or not company.google_place_id:
        logger.error(f"❌ Error: Company {company_id} has no Google Place ID in DB.")
        return None

    logger.warning(f"⚠️ CID missing for '{company.name}'. Resolving via SerpApi...")

    # Step 3: Use SerpApi to find the CID string
    resolved_cid = resolve_cid_from_google(company.google_place_id)

    if resolved_cid:
        try:
            # Step 4: SAVE PERMANENTLY to company_cids table
            new_entry = CompanyCID(
                company_id=company.id,
                cid=resolved_cid,
                place_id=company.google_place_id
            )
            db.add(new_entry)
            db.commit()
            logger.info(f"✅ AUTO-FIX SUCCESS: Saved CID {resolved_cid} for {company.name}")
            return resolved_cid
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Database Save Error: {str(e)}")
            return resolved_cid 
    
    return None

# --- 4. REVIEW INGESTION & SAVING LOGIC ---

def run_full_review_ingest(db: Session, company_id: int):
    """
    The master function to fix the CID and download reviews into the DB.
    """
    # 1. Ensure we have a CID (This handles the 'No CID found' error)
    cid = get_or_fix_company_cid(db, company_id)

    if not cid:
        logger.error(f"🛑 Aborting Ingest: Could not obtain CID for Company {company_id}")
        return

    # 2. Fetch reviews from SerpApi
    logger.info(f"🚀 Starting Review Scrape for CID: {cid}")
    
    params = {
        "engine": "google_maps_reviews",
        "data_id": cid,
        "api_key": SERPAPI_KEY,
        "hl": "en",
        "sort_by": "newest"
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        reviews_list = results.get("reviews", [])
        
        if not reviews_list:
            logger.info(f"ℹ️ No reviews found on Google for CID {cid}")
            return

        # 3. Save reviews to the 'reviews' table
        new_count = 0
        for r in reviews_list:
            review_id = r.get("review_id")
            
            # Check if this specific review is already in our DB
            existing = db.query(Review).filter(Review.google_review_id == review_id).first()
            
            if not existing:
                new_review = Review(
                    company_id=company_id,
                    google_review_id=review_id,
                    author_name=r.get("user", {}).get("name"),
                    rating=int(r.get("rating", 0)),
                    text=r.get("snippet", ""),
                    google_review_time=datetime.fromtimestamp(r.get("timestamp", datetime.now().timestamp())),
                    source_platform="Google"
                )
                db.add(new_review)
                new_count += 1
        
        db.commit()
        logger.info(f"✅ Success: Processed {len(reviews_list)} reviews. Added {new_count} new records.")

    except Exception as e:
        logger.error(f"❌ Review Ingest Error: {str(e)}")

# --- 5. INITIALIZATION (Optional: Create tables if they don't exist) ---
def init_db():
    Base.metadata.create_all(bind=engine)
