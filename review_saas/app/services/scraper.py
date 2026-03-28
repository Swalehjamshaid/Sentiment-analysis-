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

# Note: This model is for internal scraper tracking; 
# your router uses app.core.models.Review for the main app.
class GoogleReview(Base):
    __tablename__ = "google_reviews_raw"
    id = Column(Integer, primary_key=True, index=True)
    place_name = Column(String(255))
    review_id = Column(String(255), unique=True)
    author_name = Column(String(255))
    rating = Column(Float)
    text = Column(Text)
    sentiment = Column(String(50))
    sentiment_score = Column(Float)
    extracted_at = Column(DateTime, default=datetime.utcnow)

if engine:
    Base.metadata.create_all(bind=engine)

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
# ROUTER-ALIGNED FUNCTION
# =========================
async def fetch_reviews(place_id: str = None, limit: int = 20, **kwargs):
    """
    Aligned with reviews.py:
    1. Accepts place_id (ChIJ...)
    2. Returns keys: review_id, author_name, rating, text
    """
    scraper = GoogleReviewScraper()
    # If the router passes a Place ID, we try to use it, 
    # but we also allow passing 'query' for better SerpApi mapping
    search_term = place_id
    
    logging.info(f"🚀 [Scraper] Processing request for ID: {search_term}")
    
    try:
        data_id = None
        
        # STEP 1: Resolve Data ID
        # If it's a ChIJ ID, we search it to get the 'data_id' SerpApi needs
        search = GoogleSearch({
            "engine": "google_maps",
            "q": search_term,
            "api_key": scraper.api_key,
            "no_cache": True 
        })
        res = search.get_dict()
        
        place = res.get("place_results") or res.get("local_results", [{}])[0]
        data_id = place.get("data_id")
        place_name = place.get("title", "Unknown Business")

        if not data_id:
            # Fallback: Use the Place ID directly as data_id if search fails
            data_id = search_term

        # STEP 2: Fetch Reviews
        review_params = {
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": scraper.api_key,
            "num": limit,
            "no_cache": True,
            "sort_by": "newest"
        }
        
        search_reviews = GoogleSearch(review_params)
        review_data = search_reviews.get_dict().get("reviews", [])

        # STEP 3: Map to Router Schema
        final_results = []
        db = SessionLocal() if SessionLocal else None
        
        for r in review_data:
            review_body = r.get("snippet") or r.get("text") or "No comment provided"
            label, score = scraper.get_sentiment(review_body)
            
            # KEY ALIGNMENT: Match the keys expected by reviews.py loop
            review_item = {
                "review_id": r.get("review_id") or f"gen_{hash(review_body)}",
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": r.get("rating", 0),
                "text": review_body,
                "sentiment": label,
                "sentiment_score": score,
                "place_name": place_name
            }
            final_results.append(review_item)

            # Optional: Keep a raw copy in our internal scraper table
            if db:
                try:
                    raw_review = GoogleReview(
                        place_name=place_name,
                        review_id=review_item["review_id"],
                        author_name=review_item["author_name"],
                        rating=review_item["rating"],
                        text=review_item["text"],
                        sentiment=label,
                        sentiment_score=score
                    )
                    db.add(raw_review)
                except:
                    pass # Skip duplicates in raw table
        
        if db:
            db.commit()
            db.close()
            
        return final_results

    except Exception as e:
        logging.error(f"❌ Scraper Failure: {e}")
        return []
