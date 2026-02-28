# File 2: review.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company
from ..schemas import ReviewFetch
import requests, os
from datetime import datetime

router = APIRouter(prefix="/review", tags=["Review"])
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

def fetch_reviews_from_google(place_id: str):
    url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=reviews&key={GOOGLE_PLACES_API_KEY}"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=503, detail="Google API error")
    return resp.json().get("result", {}).get("reviews", [])

@router.post("/fetch")
def fetch_reviews(review_fetch: ReviewFetch, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=review_fetch.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    reviews = fetch_reviews_from_google(company.place_id)
    added_reviews = []
    for r in reviews[:500]:
        if db.query(Review).filter_by(company_id=company.id, reviewer_name=r.get("author_name")).first():
            continue
        db_review = Review(
            company_id=company.id,
            text=r.get("text", "")[:5000],
            rating=r.get("rating"),
            review_date=datetime.utcfromtimestamp(r.get("time")) if r.get("time") else datetime.utcnow(),
            reviewer_name=r.get("author_name"),
            reviewer_profile_pic=r.get("profile_photo_url"),
            fetch_status="Success",
            fetch_date=datetime.utcnow()
        )
        db.add(db_review)
        added_reviews.append(db_review)
    db.commit()
    return {"added_reviews": len(added_reviews)}
