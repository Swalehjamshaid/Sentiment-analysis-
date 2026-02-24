# review_saas/app/services/ingestion.py

import os
import logging
import googlemaps
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from ..models import Review, Company
from ..services.ai_engine import (
    analyze_sentiment,
    detect_emotions,
    extract_aspects,
    extract_keywords,
    detect_language,
    detect_anomaly
)

logger = logging.getLogger(__name__)

# Google API Client Initialization (API Health Monitoring Ready)
GOOGLE_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
gmaps = googlemaps.Client(key=GOOGLE_API_KEY)


def sync_google_reviews(db: Session, company_id: int) -> dict:
    """
    Enterprise-grade Google Reviews ingestion service.
    Fully aligned with 31 dashboard architecture requirements.
    """

    result_summary = {
        "new_reviews": 0,
        "skipped": 0,
        "errors": 0
    }

    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company or not company.place_id:
            logger.warning("Company not found or missing place_id")
            return result_summary

        # ==============================
        # 1. Google API Call (Point 1,31)
        # ==============================
        place_result = gmaps.place(
            place_id=company.place_id,
            fields=[
                'review',
                'name',
                'rating',
                'user_ratings_total'
            ],
            reviews_sort='newest'
        ).get('result', {})

        reviews_data = place_result.get('reviews', [])

        # ==============================
        # Real-Time Sync Ready (Point 2)
        # ==============================
        for g_rev in reviews_data:

            ext_id = f"gplace:{company.place_id}:{g_rev.get('author_name')}:{g_rev.get('time')}"

            exists = db.query(Review).filter(Review.external_id == ext_id).first()
            if exists:
                result_summary["skipped"] += 1
                continue

            review_text = g_rev.get('text', '')
            rating = float(g_rev.get('rating', 0))
            review_time = datetime.fromtimestamp(
                g_rev.get('time'), tz=timezone.utc
            )

            # ==============================
            # 3. Advanced Sentiment Analysis
            # ==============================
            sentiment_result = analyze_sentiment(review_text, rating)
            sentiment_category = sentiment_result["label"]
            sentiment_confidence = sentiment_result["confidence"]

            # ==============================
            # 4. Emotion Detection Layer
            # ==============================
            emotions = detect_emotions(review_text)

            # ==============================
            # 5. Aspect-Based Sentiment
            # ==============================
            aspects = extract_aspects(review_text)

            # ==============================
            # 6. Keyword Extraction
            # ==============================
            keywords = extract_keywords(review_text)

            # ==============================
            # 24. Multi-language Detection
            # ==============================
            language = detect_language(review_text)

            # ==============================
            # 27. Anomaly Detection
            # ==============================
            anomaly_flag = detect_anomaly(rating, sentiment_category, review_time)

            # ==============================
            # Review Object Mapping
            # ==============================
            new_review = Review(
                company_id=company.id,
                source="google",  # Multi-source ready
                external_id=ext_id,
                reviewer_name=g_rev.get('author_name'),
                reviewer_avatar=g_rev.get('profile_photo_url'),
                rating=rating,
                text=review_text,
                review_date=review_time,
                language=language,

                # Sentiment Layer
                sentiment_category=sentiment_category,
                sentiment_confidence=sentiment_confidence,

                # Emotion Layer
                emotions=emotions,

                # Aspect-Based Sentiment
                aspect_sentiment=aspects,

                # Keywords / Topics
                keywords=keywords,

                # Monitoring
                anomaly_flag=anomaly_flag,

                # Engagement Tracking
                response_status=False,
                response_time_hours=None
            )

            db.add(new_review)
            result_summary["new_reviews"] += 1

        db.commit()

        # ==============================
        # 23. API Health Monitoring
        # ==============================
        logger.info(f"Google API sync successful for company {company.id}")

    except SQLAlchemyError as db_err:
        db.rollback()
        logger.error(f"Database error: {db_err}")
        result_summary["errors"] += 1

    except Exception as e:
        logger.error(f"Google API or Processing Error: {e}")
        result_summary["errors"] += 1

    return result_summary
