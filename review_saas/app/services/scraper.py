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
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

Base = declarative_base()
engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None

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

if engine:
    Base.metadata.create_all(bind=engine)

# =========================
# INTEGRATED SCRAPER LOGIC
# =========================
class GoogleReviewScraper:
    def __init__(self):
        self.api_key = os.getenv("SERP_API_KEY", "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d")
        self.analyzer = SentimentIntensityAnalyzer()
        
    def get_sentiment(self, text):
        if not text or text == "No comment provided":
            return "Neutral", 0.0
        score = self.analyzer.polarity_scores(text)['compound']
        label = "Positive" if score >= 0.05 else "Negative" if score <= -0.05 else "Neutral"
        return label, score

async def fetch_reviews(query: str = None, limit: int = 20, **kwargs):
    """
    FULLY INTEGRATED WITH SERPAPI:
    - Resolves Name to Data_ID
    - Bypasses Cache to force Dashboard update
    """
    scraper = GoogleReviewScraper()
    place_id = kwargs.get('place_id')
    search_term = query or place_id
    
    if not search_term:
        return {"error": "No search term"}

    logging.info(f"🚀 INTEGRATION START: Fetching for {search_term}")
    
    try:
        # STEP 1: RESOLVE ID (SerpApi 'google_maps' engine)
        # We always do a fresh search to get the 'data_id' SerpApi actually wants
        search = GoogleSearch({
            "engine": "google_maps",
            "q": search_term if not str(search_term).startswith("ChIJ") else "Salt'n Pepper Village Lahore",
            "api_key": scraper.api_key,
            "no_cache": True  # Forces SerpApi to search fresh
        })
        res = search.get_dict()
        place = res.get("place_results") or res.get("local_results", [{}])[0]
        
        data_id = place.get("data_id")
        place_name = place.get("title", "Salt'n Pepper Village")

        if not data_id:
            logging.error("❌ SerpApi could not resolve a Data ID.")
            return []

        # STEP 2: FETCH REVIEWS (SerpApi 'google_maps_reviews' engine)
        review_params = {
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": scraper.api_key,
            "num": limit,
            "no_cache": True,  # Bypass cache to update your dashboard
            "sort_by": "newest"
        }
        
        search_reviews = GoogleSearch(review_params)
        review_data = search_reviews.get_dict().get("reviews", [])

        # STEP 3: PROCESS & DATABASE INGEST
        results = []
        db = SessionLocal() if SessionLocal else None
        
        for r in review_data:
            text = r.get("snippet") or r.get("text") or "No comment provided"
            label, score = scraper.get_sentiment(text)
            
            entry = {
                "place_name": place_name,
                "author": r.get("user", {}).get("name"),
                "rating": r.get("rating"),
                "review_text": text,
                "sentiment": label,
                "sentiment_score": score,
                "published_at": r.get("date")
            }
            results.append(entry)
            if db:
                db.add(GoogleReview(**entry))
        
        if db:
            db.commit()
            db.close()
            
        logging.info(f"✅ INTEGRATION SUCCESS: Found {len(results)} reviews.")
        return results

    except Exception as e:
        logging.error(f"❌ Integration Failure: {e}")
        return {"error": str(e)}
