
import os
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models import Review, Company
from app.services.sentiment import analyze_text, stars_to_category

logger = logging.getLogger(__name__)

try:
    import googlemaps  # type: ignore
except Exception:
    googlemaps = None

GOOGLE_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_API_KEY")

gmaps = None
if googlemaps and GOOGLE_API_KEY:
    try:
        gmaps = googlemaps.Client(key=GOOGLE_API_KEY)
    except Exception as e:
        logger.warning("Failed to init googlemaps client: %s", e)
        gmaps = None

class GoogleReviewAPI:
    @staticmethod
    def fetch_reviews(place_id: str) -> list:
        if not gmaps or not place_id:
            return []
        try:
            place_result = gmaps.place(place_id=place_id, fields=['review','name','rating','user_ratings_total']).get('result', {})
            return place_result.get('reviews', [])
        except Exception as e:
            logger.error("Google API Error for place_id %s: %s", place_id, e)
            return []


def sync_google_reviews(db: Session, company_id: int) -> dict:
    result_summary = {"new_reviews": 0, "skipped": 0, "errors": 0}
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company or not company.place_id:
            logger.warning("Company not found or missing place_id")
            return result_summary

        reviews_data = GoogleReviewAPI.fetch_reviews(company.place_id)
        for g_rev in reviews_data:
            ext_id = f"gplace:{company.place_id}:{g_rev.get('author_name')}:{g_rev.get('time')}"
            exists = db.query(Review).filter(Review.external_id == ext_id, Review.company_id == company.id).first()
            if exists:
                result_summary["skipped"] += 1
                continue

            review_text = g_rev.get('text', '')
            rating_val = g_rev.get('rating', None)
            rating = int(rating_val) if rating_val is not None else None
            review_time = None
            ts = g_rev.get('time')
            if ts is not None:
                try:
                    review_time = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                except Exception:
                    review_time = None

            cat, score, keywords, lang = analyze_text(review_text)
            if rating is not None and not cat:
                cat = stars_to_category(rating)

            new_review = Review(
                company_id=company.id,
                source='google',
                external_id=ext_id,
                reviewer_name=g_rev.get('author_name'),
                reviewer_avatar=g_rev.get('profile_photo_url'),
                rating=rating,
                text=review_text,
                review_date=review_time,
                language=lang,
                sentiment_category=cat,
                sentiment_score=score,
                keywords=",".join(keywords) if keywords else None,
            )

            db.add(new_review)
            result_summary["new_reviews"] += 1

        db.commit()
        logger.info("Google API sync successful for company %s", company.id)
        company.last_synced_at = datetime.now(timezone.utc)
        company.last_sync_status = "Healthy"
        db.commit()

    except SQLAlchemyError as db_err:
        db.rollback()
        logger.error("Database error: %s", db_err)
        result_summary["errors"] += 1

    except Exception as e:
        logger.error("Google API or Processing Error: %s", e)
        result_summary["errors"] += 1

    return result_summary
