# filename: app/routes/reviews.py
from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse
import logging

from app.core.db import get_session
from app.core.models import Company
# Fixed: Importing the bridge function that we just added to services
from app.services.google_reviews import fetch_place_details

router = APIRouter(prefix="/google", tags=['google_api'])
logger = logging.getLogger(__name__)

@router.get('/details')
async def google_place_details(place_id: str = Query(...)):
    """
    Fetches raw details from Google for the search/preview feature.
    """
    try:
        # Calls the bridge function in services/google_reviews.py
        details = await fetch_place_details(place_id)
        
        if not details or details.get('status') != 'OK':
            return JSONResponse(
                status_code=400, 
                content={"status": "error", "message": "Invalid Place ID or API error"}
            )
            
        return details.get('result', {})
    except Exception as e:
        logger.error(f"Error fetching Google details: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/preview/{place_id}')
async def google_reviews_preview(place_id: str):
    """
    Returns a quick preview of reviews before a user decides to import the company.
    """
    details = await fetch_place_details(place_id)
    result = details.get('result', {})
    
    return {
        "name": result.get('name'),
        "rating": result.get('rating'),
        "review_count": result.get('user_ratings_total'),
        "sample_reviews": result.get('reviews', [])[:3] # Show first 3 only
    }
