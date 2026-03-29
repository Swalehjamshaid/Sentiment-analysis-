from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests
import os
import logging

# =========================
# INIT
# =========================
router = APIRouter()
logger = logging.getLogger(__name__)

SERP_API_KEY = os.getenv("SERP_API_KEY")


# =========================
# REQUEST MODEL (Dashboard)
# =========================
class ReviewRequest(BaseModel):
    place_id: str


# =========================
# CORE FUNCTION
# =========================
def fetch_reviews_from_serpapi(place_id: str):
    if not SERP_API_KEY:
        raise Exception("SERP_API_KEY not set")

    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google_maps_reviews",
        "place_id": place_id,
        "api_key": SERP_API_KEY
    }

    response = requests.get(url, params=params)
    data = response.json()

    reviews = []

    for r in data.get("reviews", []):
        reviews.append({
            "user": r.get("user", {}).get("name"),
            "rating": r.get("rating"),
            "comment": r.get("snippet"),
            "date": r.get("date")
        })

    return reviews


# =========================
# POST API (Dashboard Trigger)
# =========================
@router.post("/reviews/fetch")
def fetch_reviews(payload: ReviewRequest):
    """
    Triggered from dashboard
    """
    try:
        logger.info(f"📥 Fetching reviews for place_id: {payload.place_id}")

        reviews = fetch_reviews_from_serpapi(payload.place_id)

        return {
            "status": "success",
            "total_reviews": len(reviews),
            "reviews": reviews
        }

    except Exception as e:
        logger.error(f"❌ Error fetching reviews: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# GET API (Testing)
# =========================
@router.get("/reviews")
def get_reviews(place_id: str):
    """
    For browser testing
    Example: /api/reviews?place_id=XXXX
    """
    try:
        reviews = fetch_reviews_from_serpapi(place_id)

        return {
            "status": "success",
            "total_reviews": len(reviews),
            "reviews": reviews
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
