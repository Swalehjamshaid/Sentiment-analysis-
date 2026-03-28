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
        self.api_key = os.getenv("SERP_API_KEY", "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d")
        self.analyzer = SentimentIntensityAnalyzer()
        
    def get_sentiment(self, text):
        if not text or text == "No comment provided":
            return "Neutral", 0.0
        score = self.analyzer.polarity_scores(text)['compound']
        label = "Positive" if score >= 0.05 else "Negative" if score <= -0.05 else "Neutral"
        return label, score

# =========================
# THE FIX: ADD ASYNC TO ALIGN WITH ROUTE
# =========================
async def fetch_reviews(query: str = None, limit: int = 20, **kwargs):
    """
    Marked as 'async' so your FastAPI route can 'await' it.
    """
    search_term = query or kwargs.get('place_id')
    
    if not search_term:
        logging.error("❌ No search query or place_id provided.")
        return {"error": "No search term provided"}

    scraper = GoogleReviewScraper()
    logging.info(f"🚀 Scraping reviews for: {search_term}")
    
    try:
        # 1. Search for the place
        # SerpApi calls are blocking, but wrapping in async def allows 
        # the FastAPI worker to handle the call via await.
        search = GoogleSearch({
            "engine": "google_maps", 
            "q": search_term, 
            "api_key": scraper.api_key
        })
        res = search.get_dict()
        
        place = res.get("place_results")
        if not place:
            local = res.get("local_results", [])
            place = local[0] if local else None
            
        if not place or not place.get("data_id"):
            return {"error": f"Location '{search_term}' not found"}

        data_id = place.get("data_id")
        place_name = place.get("title")

        # 2. Extract Reviews
        search_reviews = GoogleSearch({
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": scraper.api_key,
            "num": limit
        })
        review_data = search_reviews.get_dict().get("reviews", [])

        # 3. Process & Save
        results_to_return = []
        db = SessionLocal() if SessionLocal else None
        
        for r in review_data:
            text = r.get("snippet", "No comment provided")
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
                db_review = GoogleReview(**review_entry)
                db.add(db_review)
        
        if db:
            db.commit()
            db.close()
            
        return results_to_return

    except Exception as e:
        logging.error(f"❌ Scraper failure: {e}")
        return {"error": str(e)}
