import os
import logging
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from serpapi import GoogleSearch
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# =================================================================
# 1. DATABASE CONFIGURATION
# =================================================================
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

Base = declarative_base()
engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None

class GoogleReviewRaw(Base):
    __tablename__ = "google_reviews_raw"
    id = Column(Integer, primary_key=True)
    review_id = Column(String(255), unique=True)
    author_name = Column(String(255))
    rating = Column(Float)
    text = Column(Text)
    sentiment = Column(String(50))
    extracted_at = Column(DateTime, default=datetime.utcnow)

if engine:
    Base.metadata.create_all(bind=engine)

# =================================================================
# 2. THE FINAL RESOLVER SCRAPER
# =================================================================
async def fetch_reviews(place_id: str = None, limit: int = 300, **kwargs):
    """
    CRITICAL FIX: 
    Uses the company name passed from the router to ensure 
    fallback searches are precise (e.g., 'Salt'n Pepper' instead of 'Google Business').
    """
    api_key = os.getenv("SERP_API_KEY", "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d")
    analyzer = SentimentIntensityAnalyzer()
    
    target_id = place_id
    # If the router doesn't pass 'name', we use this hardcoded map for your specific DB entries
    target_name = kwargs.get('name')
    
    if not target_name or target_name == "Google Business":
        id_map = {
            "ChIJe2LWbaIIGTkRZhr_Fbyvkvs": "Gloria Jeans Coffees DHA Phase 5 Lahore",
            "ChIJDVYKpFEEGTkRp_XASXZ21Tc": "Salt'n Pepper Village Lahore",
            "ChIJ8S6kk9YJGtkRWK6XHzCKsrA": "McDonald's Lahore"
        }
        target_name = id_map.get(target_id, "Restaurant Lahore")

    logging.info(f"🚀 [Scraper] Ingesting: {target_name} ({target_id})")
    
    try:
        # STEP 1: RESOLVE PLACE ID TO CID
        search_resolver = GoogleSearch({
            "engine": "google_maps",
            "place_id": target_id,
            "api_key": api_key,
            "no_cache": True 
        })
        res = search_resolver.get_dict()
        data_id = res.get("place_results", {}).get("data_id")

        # STEP 2: PRECISION FALLBACK
        if not data_id:
            logging.warning(f"⚠️ ID Resolution failed. Searching by Name: {target_name}")
            search_fb = GoogleSearch({
                "engine": "google_maps",
                "q": target_name,
                "api_key": api_key
            })
            fb_res = search_fb.get_dict()
            local = fb_res.get("local_results", [])
            place_fb = fb_res.get("place_results") or (local[0] if local else {})
            data_id = place_fb.get("data_id")

        if not data_id:
            logging.error(f"❌ Failed to find CID for {target_name}")
            return []

        # STEP 3: FETCH ACTUAL REVIEWS
        logging.info(f"📍 CID Resolved: {data_id}. Fetching reviews...")
        review_params = {
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": api_key,
            "num": limit,
            "no_cache": True,
            "sort_by": "newest"
        }
        
        search_reviews = GoogleSearch(review_params)
        raw_reviews = search_reviews.get_dict().get("reviews", [])

        # STEP 4: DATA MAPPING FOR REVIEWS.PY
        final_results = []
        for r in raw_reviews:
            body = r.get("snippet") or r.get("text") or "No comment"
            vs = analyzer.polarity_scores(body)
            
            final_results.append({
                "review_id": r.get("review_id"),
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": r.get("rating", 0),
                "text": body,
                "sentiment": "Positive" if vs['compound'] >= 0.05 else "Negative"
            })
        
        logging.info(f"✅ Success: Captured {len(final_results)} reviews.")
        return final_results

    except Exception as e:
        logging.error(f"❌ Scraper failure: {e}")
        return []
