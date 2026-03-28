import os
import logging
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from serpapi import GoogleSearch
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# =========================
# CONFIGURATION & DATABASE
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("RailwayScraper")

# Railway provides a DATABASE_URL environment variable automatically
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/postgres")
# Fix for SQLAlchemy if Railway uses 'postgres://' instead of 'postgresql://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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

# Create tables in Railway
Base.metadata.create_all(bind=engine)

# =========================
# SCRAPER CLASS
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

    def run_pipeline(self, query, limit=20):
        try:
            # 1. Search for Location
            search = GoogleSearch({"engine": "google_maps", "q": query, "api_key": self.api_key})
            res = search.get_dict()
            place = res.get("place_results") or res.get("local_results", [{}])[0]
            
            data_id = place.get("data_id")
            place_name = place.get("title")
            
            if not data_id:
                logger.error("Location not found.")
                return

            # 2. Fetch Reviews
            logger.info(f"Scraping {place_name}...")
            search_reviews = GoogleSearch({
                "engine": "google_maps_reviews",
                "data_id": data_id,
                "api_key": self.api_key,
                "num": limit
            })
            review_data = search_reviews.get_dict().get("reviews", [])

            # 3. Save to Railway Database
            db = SessionLocal()
            for r in review_data:
                text = r.get("snippet", "No comment provided")
                label, score = self.get_sentiment(text)
                
                new_review = GoogleReview(
                    place_name=place_name,
                    author=r.get("user", {}).get("name"),
                    rating=r.get("rating"),
                    review_text=text,
                    sentiment=label,
                    sentiment_score=score,
                    published_at=r.get("date")
                )
                db.add(new_review)
            
            db.commit()
            db.close()
            logger.info(f"✅ Successfully saved {len(review_data)} reviews to Railway Database.")

        except Exception as e:
            logger.error(f"❌ Pipeline failed: {e}")

# =========================
# EXECUTION
# =========================
if __name__ == "__main__":
    scraper = GoogleReviewScraper()
    # Change this to any landmark or business
    target = "Badshahi Mosque Lahore"
    scraper.run_pipeline(target, limit=20)
