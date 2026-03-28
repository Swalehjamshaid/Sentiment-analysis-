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
# Correctly parsing your Railway DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

Base = declarative_base()
engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None

# Raw table for scraper logs
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
# SERPAPI INTEGRATED LOGIC
# =========================
async def fetch_reviews(place_id: str = None, limit: int = 300, **kwargs):
    """
    INTEGRATED WITH SERP_API_KEY
    - Fetches up to 300 reviews as requested by your router.
    - Matches 'review_id', 'author_name', 'rating', and 'text' keys.
    """
    # Pull the key from your Railway Environment Variables
    api_key = os.getenv("SERP_API_KEY", "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d")
    analyzer = SentimentIntensityAnalyzer()
    
    # Priority: Name Search > Place ID
    search_term = kwargs.get('name') or place_id
    logging.info(f"🚀 SerpApi Integration: Ingesting reviews for {search_term}")

    try:
        # STEP 1: Find the internal SerpApi Data ID
        search = GoogleSearch({
            "engine": "google_maps",
            "q": search_term,
            "api_key": api_key,
            "no_cache": True 
        })
        res = search.get_dict()
        local = res.get("local_results", [])
        place = res.get("place_results") or (local[0] if local else {})
        data_id = place.get("data_id") or place_id

        if not data_id:
            logging.error(f"❌ Failed to resolve data_id for {search_term}")
            return []

        # STEP 2: Fetch reviews with newest sorting
        review_params = {
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": api_key,
            "num": limit,
            "no_cache": True,
            "sort_by": "newest"
        }
        
        search_reviews = GoogleSearch(review_params)
        results_dict = search_reviews.get_dict()
        review_data = results_dict.get("reviews", [])

        # STEP 3: Format and Analyze Sentiment
        final_output = []
        for r in review_data:
            content = r.get("snippet") or r.get("text") or "No comment provided"
            
            # Vader Sentiment Analysis
            vs = analyzer.polarity_scores(content)
            sentiment_label = "Positive" if vs['compound'] >= 0.05 else "Negative" if vs['compound'] <= -0.05 else "Neutral"
            
            # Key alignment for app/routes/reviews.py
            final_output.append({
                "review_id": r.get("review_id"),
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": r.get("rating", 0),
                "text": content,
                "sentiment": sentiment_label,
                "sentiment_score": vs['compound']
            })
        
        logging.info(f"✅ Integration Success: {len(final_output)} reviews ready for ingest.")
        return final_output

    except Exception as e:
        logging.error(f"❌ SerpApi Integration Crash: {e}")
        return []
