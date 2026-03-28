import os
import logging
import asyncio
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
    google_review_id = Column(String(255), unique=True, index=True)  # ✅ important fix
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
# SCRAPER CLASS
# =========================
class GoogleReviewScraper:
    def __init__(self):
        self.api_key = os.getenv("SERP_API_KEY")

        if not self.api_key:
            raise ValueError("❌ SERP_API_KEY not found in environment variables")

        self.analyzer = SentimentIntensityAnalyzer()

        logging.info(f"🔑 SerpAPI Key Loaded: {self.api_key[:5]}*****")

    def get_sentiment(self, text):
        if not text or text == "No comment provided":
            return "Neutral", 0.0

        score = self.analyzer.polarity_scores(text)['compound']

        if score >= 0.05:
            return "Positive", score
        elif score <= -0.05:
            return "Negative", score
        return "Neutral", score

# =========================
# MAIN FUNCTION (ASYNC SAFE)
# =========================
async def fetch_reviews(query: str = None, limit: int = 20, **kwargs):

    search_term = query
    place_id = kwargs.get("place_id")

    if not search_term and not place_id:
        return {"success": False, "error": "No query or place_id provided"}

    scraper = GoogleReviewScraper()

    try:
        # =========================
        # STEP 1: GET PLACE DATA_ID
        # =========================
        if place_id:
            data_id = place_id
            place_name = "Unknown"
        else:
            search = GoogleSearch({
                "engine": "google_maps",
                "q": search_term,
                "api_key": scraper.api_key
            })

            res = await asyncio.to_thread(search.get_dict)

            if not res:
                return {"success": False, "error": "SerpAPI failed to respond"}

            place = res.get("place_results") or (res.get("local_results") or [{}])[0]

            if not place or not place.get("data_id"):
                return {"success": False, "error": f"Location '{search_term}' not found"}

            data_id = place.get("data_id")
            place_name = place.get("title")

        logging.info(f"📍 Data ID: {data_id}")

        # =========================
        # STEP 2: GET REVIEWS
        # =========================
        search_reviews = GoogleSearch({
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": scraper.api_key,
            "num": limit
        })

        review_response = await asyncio.to_thread(search_reviews.get_dict)
        review_data = review_response.get("reviews", [])

        if not isinstance(review_data, list):
            return {"success": False, "error": "Invalid review data format"}

        # =========================
        # STEP 3: PROCESS REVIEWS
        # =========================
        results = []
        db = SessionLocal() if SessionLocal else None

        try:
            for r in review_data:

                if not isinstance(r, dict):
                    logging.warning(f"⚠️ Skipping invalid item: {r}")
                    continue

                review_id = r.get("review_id")
                if not review_id:
                    continue

                text = r.get("snippet", "No comment provided")
                label, score = scraper.get_sentiment(text)

                review_entry = {
                    "google_review_id": review_id,
                    "place_name": place_name,
                    "author": r.get("user", {}).get("name"),
                    "rating": r.get("rating"),
                    "review_text": text,
                    "sentiment": label,
                    "sentiment_score": score,
                    "published_at": r.get("date")
                }

                results.append(review_entry)

                # =========================
                # SAVE TO DB (NO DUPLICATES)
                # =========================
                if db:
                    existing = db.query(GoogleReview).filter_by(
                        google_review_id=review_id
                    ).first()

                    if not existing:
                        db.add(GoogleReview(**review_entry))

            if db:
                db.commit()

        finally:
            if db:
                db.close()

        return {
            "success": True,
            "count": len(results),
            "data": results
        }

    except Exception as e:
        logging.error(f"❌ Scraper failure: {e}")
        return {"success": False, "error": str(e)}
