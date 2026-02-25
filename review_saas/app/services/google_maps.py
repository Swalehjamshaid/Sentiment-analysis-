import os
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from ..models import Review, Company

# You will need to install googlemaps: pip install googlemaps
import googlemaps

logger = logging.getLogger("review_saas")

async def sync_company_reviews(db: Session, company: Company) -> int:
    """
    Fetches reviews from Google Maps for a specific company and saves them to DB.
    Returns the number of new reviews added.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        logger.error("GOOGLE_MAPS_API_KEY not found in environment variables.")
        return 0

    if not company.place_id:
        logger.warning(f"Company {company.name} has no Place ID. Skipping sync.")
        return 0

    try:
        gmaps = googlemaps.Client(key=api_key)
        
        # 1. Fetch place details (specifically reviews)
        # Note: Google API returns the 5 most helpful reviews by default.
        # For a full history, you would typically use a webhook or the My Business API.
        place_details = gmaps.place(
            place_id=company.place_id,
            fields=['review', 'name']
        )

        reviews_data = place_details.get('result', {}).get('reviews', [])
        new_reviews_count = 0

        for r_data in reviews_data:
            # Check if review already exists to avoid duplicates
            # We use a combination of reviewer name and timestamp as a unique check
            existing = db.query(Review).filter(
                Review.company_id == company.id,
                Review.reviewer_name == r_data.get('author_name'),
                Review.text == r_data.get('text')
            ).first()

            if not existing:
                # Convert Google's unix timestamp to Python datetime
                rev_date = datetime.fromtimestamp(r_data.get('time'))
                
                new_review = Review(
                    company_id=company.id,
                    reviewer_name=r_data.get('author_name'),
                    rating=r_data.get('rating'),
                    text=r_data.get('text'),
                    review_date=rev_date,
                    language=r_data.get('language', 'en'),
                    # Initial sentiment as 'Neutral' until AI processing kicks in
                    sentiment_category='Neutral',
                    sentiment_score=0.5
                )
                db.add(new_review)
                new_reviews_count += 1

        db.commit()
        return new_reviews_count

    except Exception as e:
        logger.error(f"Google Maps API Error for {company.name}: {str(e)}")
        db.rollback()
        raise e
