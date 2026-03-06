# File: app/routes/reviews.py

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from app.services.google_reviews import ingest_company_reviews, OutscraperReviewsService

# Initialize router
router = APIRouter(prefix="/reviews", tags=["reviews"])

# Initialize the service
outscraper_service = OutscraperReviewsService()


# -------------------- Ingest reviews for a company --------------------
@router.post("/ingest/{place_id}/{company_id}")
async def ingest_reviews(
    place_id: str,
    company_id: int,
    limit: Optional[int] = Query(1000, description="Max number of reviews to fetch")
):
    """
    Ingest reviews for a company using Outscraper.
    Supports a limit parameter to fetch more than 5 reviews.
    """
    try:
        # Fetch reviews from Outscraper
        reviews_data = await outscraper_service.fetch_reviews(place_id, limit=limit)
        
        # Save unique reviews to database
        await ingest_company_reviews(place_id, company_id)
        
        return {
            "status": "success",
            "message": f"Ingested {len(reviews_data)} reviews for company {company_id}",
            "reviews_fetched": len(reviews_data)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest reviews: {str(e)}")


# -------------------- Fetch reviews for competitors --------------------
@router.post("/competitor-analysis/")
async def competitor_analysis(
    queries: List[str],
    limit: Optional[int] = Query(500, description="Max reviews per competitor")
) -> Dict[str, Any]:
    """
    Fetch reviews for multiple competitors at once.
    Accepts a list of competitor names or place_ids in `queries`.
    """
    try:
        all_data: Dict[str, List[Dict[str, Any]]] = {}
        for q in queries:
            reviews = await outscraper_service.fetch_reviews(q, limit=limit)
            all_data[q] = reviews
        return {"status": "success", "data": all_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed competitor analysis: {str(e)}")


# -------------------- Optional: Fetch single place details --------------------
@router.get("/place-details/{place_id}")
async def fetch_place_details(place_id: str):
    """
    Placeholder endpoint for fetching place details.
    Can be extended later to use Outscraper or Google Business Profile API.
    """
    try:
        details = await outscraper_service.fetch_reviews(place_id, limit=1)  # just a sample
        return {"status": "success", "place_id": place_id, "sample_data": details}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch place details: {str(e)}")
