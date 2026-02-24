import googlemaps
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..models import Review, Company

# Initialize the client with your key
gmaps = googlemaps.Client(key=os.getenv("GOOGLE_PLACES_API_KEY"))

def sync_google_reviews(db: Session, company_id: int):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company or not company.place_id:
        return 0

    # 1. Power up the Google API Request
    # Note: Google Places Details is limited to the 5 most 'relevant' reviews
    place_result = gmaps.place(
        place_id=company.place_id,
        fields=['review', 'name', 'rating'],
        reviews_sort='newest'  # Get the latest ones
    ).get('result', {})

    reviews_data = place_result.get('reviews', [])
    new_count = 0

    for g_rev in reviews_data:
        # Create a unique external ID to prevent duplicates
        # Format: gplace:{place_id}:{author_name}:{timestamp}
        ext_id = f"gplace:{company.place_id}:{g_rev.get('author_name')}:{g_rev.get('time')}"
        
        exists = db.query(Review).filter(Review.external_id == ext_id).first()
        if not exists:
            # 2. Map Google Data to your Dashboard Schema
            new_review = Review(
                company_id=company.id,
                external_id=ext_id,
                reviewer_name=g_rev.get('author_name'),
                reviewer_avatar=g_rev.get('profile_photo_url'),
                rating=float(g_rev.get('rating')),
                text=g_rev.get('text'),
                review_date=datetime.fromtimestamp(g_rev.get('time'), tz=timezone.utc),
                language=g_rev.get('language'),
                # Autonomous Sentiment Logic
                sentiment_category="Positive" if g_rev.get('rating') >= 4 else 
                                  ("Negative" if g_rev.get('rating') <= 2 else "Neutral")
            )
            db.add(new_review)
            new_count += 1
    
    db.commit()
    return new_count
