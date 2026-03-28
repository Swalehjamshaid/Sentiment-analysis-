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

# Alignment: Force Psycopg 3 dialect for Railway/SQLAlchemy compatibility
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

Base = declarative_base()
engine = None
SessionLocal = None

if DATABASE_URL:
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    except Exception as e:
        logging.error(f"❌ Database Engine Error: {e}")

# =========================
# DATABASE MODEL
# =========================
class GoogleReview(Base):
    __tablename__ = "google_reviews"
    
    id = Column(Integer, primary_key=True, index=True)
    place_name = Column(String(255))
    author = Column(String(255))
    rating = Column(Float)
    review_text = Column(Text)
    sentiment = Column(String(50))
    sentiment_score = Column(Float)
    published_at = Column(String(100))
    extracted_at = Column(DateTime, default=datetime.utcnow)

# Ensure table exists
if engine:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logging.error(f"❌ Table creation failed: {e}")

# =========================
# SCRAPER LOGIC
# =========================
class GoogleReviewScraper:
    def __init__(self):
        # API Key from your screenshot
        self.api_key = os.getenv("SERP_API_KEY", "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d")
        self.analyzer = SentimentIntensityAnalyzer()
        
    def get_sentiment(self, text):
        if not text or text == "No comment provided":
            return "Neutral", 0.0
        score = self.analyzer.polarity_scores(text)['compound']
        label = "Positive" if score >= 0.05 else "Negative" if score <= -0.05 else "Neutral"
        return label, score

# =========================
# THE FIX: ASYNC & PLACE_ID ALIGNMENT
# =========================
async def fetch_reviews(query: str = None, limit: int = 20, **kwargs):
    """
    Final optimized function to bridge FastAPI with SerpApi.
    Handles 'place_id' directly to fix 0-review results.
    """
    # Detect place_id if provided by the route
    place_id = kwargs.get('place_id')
    search_term = query or place_id
    
    if not search_term:
        logging.error("❌ No search query or place_id provided.")
        return {"error": "No search term provided"}

    scraper = GoogleReviewScraper()
    logging.info(f"🚀 Initializing Deep-Scrape for: {search_term}")
    
    try:
        data_id = None
        place_name = search_term

        # STEP 1: Determine if we use direct ID or search
        if str(search_term).startswith("ChIJ"):
            data_id = search_term
            logging.info(f"📍 Using direct Place ID: {data_id}")
        else:
            search = GoogleSearch({
                "engine": "google_maps", 
                "q": search_term, 
                "api_key": scraper.api_key
            })
            res = search.get_dict()
            place = res.get("place_results") or res.get("local_results", [{}])[0]
            data_id = place.get("data_id")
            place_name = place.get("title", search_term)

        if not data_id:
            return {"error": "Location not found"}

        # STEP 2: Fetch reviews
        search_reviews = GoogleSearch({
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": scraper.api_key,
            "num": limit
        })
        
        response_dict = search_reviews.get_dict()
        review_data = response_dict.get("reviews", [])

        # STEP 3: Process & Save to Railway DB
        results_to_return = []
        db = SessionLocal() if SessionLocal else None
        
        for r in review_data:
            # Fallback for review content
            text = r.get("snippet") or r.get("text") or "No comment provided"
            label, score = scraper.get_sentiment(text)
            
            review_entry = {
                "place_name": place_name,
                "author": r.get("user", {}).get("name"),
                "rating": r.get("rating"),
                "review_text": text,
                "sentiment": label,
                "sentiment_score": score,
                "published_at": r.get("date")
            }
            results_to_return.append(review_entry)

            if db:
                db_obj = GoogleReview(**review_entry)
                db.add(db_obj)
        
        if db:
            db.commit()
            db.close()
            
        logging.info(f"✅ Captured {len(results_to_return)} reviews.")
        return results_to_return

    except Exception as e:
        logging.error(f"❌ Scraper failure: {e}")
        return {"error": str(e)}
