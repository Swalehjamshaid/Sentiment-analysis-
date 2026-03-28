import os
import logging
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from serpapi import GoogleSearch
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# =========================
# DATABASE CONFIGURATION
# =========================
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)

Base = declarative_base()
engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None

class GoogleReviewRaw(Base):
    __tablename__ = "google_reviews_raw"
    id = Column(Integer, primary_key=True)
    review_id = Column(String(255), unique=True)
    author_name = Column(String(255))
    text = Column(Text)
    sentiment = Column(String(50))
    extracted_at = Column(DateTime, default=datetime.utcnow)

if engine:
    Base.metadata.create_all(bind=engine)

# =========================
# THE "PLACE ID RESOLVER" SCRAPER
# =========================
async def fetch_reviews(place_id: str = None, limit: int = 300, **kwargs):
    """
    ALIGNED WITH YOUR DATABASE:
    - Takes the 'ChIJ...' Place ID from your database.
    - Resolves it to a CID (Data ID) via SerpApi.
    - Fetches the reviews and returns them for ingest.
    """
    api_key = os.getenv("SERP_API_KEY", "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d")
    analyzer = SentimentIntensityAnalyzer()
    
    # We use the Place ID passed from the route (e.g., ChIJe2LWbaIIGTkRZhr_Fbyvkvs)
    target_id = place_id or kwargs.get('place_id')
    
    if not target_id:
        logging.error("❌ No Place ID provided from database.")
        return []

    logging.info(f"🚀 [Scraper] Resolving Database Place ID: {target_id}")

    try:
        # STEP 1: RESOLVE PLACE ID TO DATA_ID (CID)
        # We use the 'google_maps' engine with the specific place_id parameter
        search = GoogleSearch({
            "engine": "google_maps",
            "place_id": target_id, # Using the exact key for Place IDs
            "api_key": api_key,
            "no_cache": True 
        })
        res = search.get_dict()
        
        # Get the internal data_id (CID) required for the Review Engine
        place_info = res.get("place_results", {})
        data_id = place_info.get("data_id")
        place_name = place_info.get("title", "Google Maps Business")

        if not data_id:
            logging.warning(f"⚠️ Could not resolve CID for {target_id}. Falling back to name search.")
            # If place_id fails, we use the name if available
            name_query = kwargs.get('name', 'Restaurant Lahore')
            search_fallback = GoogleSearch({"engine": "google_maps", "q": name_query, "api_key": api_key})
            res_fb = search_fallback.get_dict()
            data_id = (res_fb.get("place_results") or res_fb.get("local_results", [{}])[0]).get("data_id")

        if not data_id:
            logging.error(f"❌ Failed to find a valid Data ID for {target_id}")
            return []

        # STEP 2: FETCH REVIEWS USING DATA_ID
        logging.info(f"📍 CID Resolved: {data_id}. Pulling {limit} reviews...")
        review_params = {
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": api_key,
            "num": limit,
            "no_cache": True,
            "sort_by": "newest"
        }
        
        search_reviews = GoogleSearch(review_params)
        review_data = search_reviews.get_dict().get("reviews", [])

        # STEP 3: FORMAT FOR REVIEWS.PY ROUTER
        final_results = []
        for r in review_data:
            review_body = r.get("snippet") or r.get("text") or "No comment provided"
            vs = analyzer.polarity_scores(review_body)
            
            # KEY ALIGNMENT for your router: review_id, author_name, rating, text
            final_results.append({
                "review_id": r.get("review_id") or f"db_{hash(review_body)}",
                "author_name": r.get("user", {}).get("name", "Anonymous User"),
                "rating": r.get("rating", 0),
                "text": review_body,
                "sentiment": "Positive" if vs['compound'] >= 0.05 else "Negative" if vs['compound'] <= -0.05 else "Neutral"
            })
        
        logging.info(f"✅ Success: Resolved {target_id} and captured {len(final_results)} reviews.")
        return final_results

    except Exception as e:
        logging.error(f"❌ Scraper Critical failure: {e}")
        return []
