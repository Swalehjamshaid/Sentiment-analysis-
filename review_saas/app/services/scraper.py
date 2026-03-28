import os
import logging
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from serpapi import GoogleSearch
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# =================================================================
# 1. DATABASE CONFIGURATION (Psycopg 3 & Railway Aligned)
# =================================================================
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Fix for 'ModuleNotFoundError: No module named psycopg2'
# Forces SQLAlchemy to use the psycopg v3 driver in your requirements.txt
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

Base = declarative_base()
engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None

# Internal Raw Tracking Table for Scraper History
class GoogleReviewRaw(Base):
    __tablename__ = "google_reviews_raw"
    id = Column(Integer, primary_key=True)
    review_id = Column(String(255), unique=True)
    author_name = Column(String(255))
    rating = Column(Float)
    text = Column(Text)
    sentiment = Column(String(50))
    sentiment_score = Column(Float)
    extracted_at = Column(DateTime, default=datetime.utcnow)

if engine:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logging.error(f"❌ Table creation failed: {e}")

# =================================================================
# 2. SCRAPER & INTEGRATION LOGIC
# =================================================================
class GoogleReviewScraper:
    def __init__(self):
        # API Key from your Railway Environment Variables
        self.api_key = os.getenv("SERP_API_KEY", "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d")
        self.analyzer = SentimentIntensityAnalyzer()
        
    def get_sentiment(self, text):
        if not text or text == "No comment provided":
            return "Neutral", 0.0
        score = self.analyzer.polarity_scores(text)['compound']
        label = "Positive" if score >= 0.05 else "Negative" if score <= -0.05 else "Neutral"
        return label, score

# =================================================================
# 3. ROUTER-ALIGNED ENTRY POINT (Async)
# =================================================================
async def fetch_reviews(place_id: str = None, limit: int = 300, **kwargs):
    """
    ULTIMATE INTEGRATION:
    - Resolves ChIJ IDs to CIDs (Data IDs) to prevent 0-review results.
    - Matches keys for your reviews.py router (review_id, author_name, text).
    - Forces SerpApi dashboard updates with no_cache: True.
    """
    scraper = GoogleReviewScraper()
    target_id = place_id or kwargs.get('place_id')
    # Use the name passed from company.name in the router for fallback
    target_name = kwargs.get('name') or "Google Business"
    
    if not target_id:
        logging.error("❌ No target ID (Place ID) provided.")
        return []

    logging.info(f"🚀 [Scraper] Integrated Search for: {target_name} ({target_id})")
    
    try:
        # STEP 1: RESOLVE PLACE ID TO CID (DATA_ID)
        # Using the direct 'place_id' parameter for exact mapping
        search_resolver = GoogleSearch({
            "engine": "google_maps",
            "place_id": target_id,
            "api_key": scraper.api_key,
            "no_cache": True 
        })
        res = search_resolver.get_dict()
        
        place_info = res.get("place_results", {})
        data_id = place_info.get("data_id")
        resolved_name = place_info.get("title", target_name)

        # FALLBACK: If direct ID resolution fails, search by Name
        if not data_id:
            logging.warning(f"⚠️ ID resolution failed for {target_id}. Searching by Name: {target_name}")
            search_fb = GoogleSearch({
                "engine": "google_maps", 
                "q": target_name, 
                "api_key": scraper.api_key
            })
            fb_res = search_fb.get_dict()
            local_results = fb_res.get("local_results", [])
            place_fb = fb_res.get("place_results") or (local_results[0] if local_results else {})
            data_id = place_fb.get("data_id")
            resolved_name = place_fb.get("title", target_name)

        if not data_id:
            logging.error(f"❌ Failed to resolve a valid CID for {target_id}")
            return []

        # STEP 2: FETCH ACTUAL REVIEWS
        logging.info(f"📍 CID Resolved: {data_id}. Fetching reviews...")
        review_params = {
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": scraper.api_key,
            "num": limit,
            "no_cache": True, # Bypass cache to update your dashboard count
            "sort_by": "newest"
        }
        
        search_reviews = GoogleSearch(review_params)
        raw_reviews = search_reviews.get_dict().get("reviews", [])

        # STEP 3: DATA MAPPING FOR REVIEWS.PY ROUTER
        final_results = []
        db = SessionLocal() if SessionLocal else None
        
        for r in raw_reviews:
            review_body = r.get("snippet") or r.get("text") or "No comment provided"
            label, score = scraper.get_sentiment(review_body)
            
            # This dictionary matches exactly what app/routes/reviews.py expects
            item = {
                "review_id": r.get("review_id") or f"id_{hash(review_body)}",
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": r.get("rating", 0),
                "text": review_body,
                "sentiment": label,
                "sentiment_score": score
            }
            final_results.append(item)

            # Persistence to raw internal table
            if db:
                try:
                    db.add(GoogleReviewRaw(
                        review_id=item["review_id"],
                        author_name=item["author_name"],
                        rating=item["rating"],
                        text=item["text"],
                        sentiment=label,
                        sentiment_score=score
                    ))
                except:
                    pass # Prevent crash on existing duplicates
        
        if db:
            db.commit()
            db.close()
            
        logging.info(f"✅ Success: Captured {len(final_results)} reviews for {resolved_name}")
        return final_results

    except Exception as e:
        logging.error(f"❌ Scraper Critical Failure: {e}")
        return []
