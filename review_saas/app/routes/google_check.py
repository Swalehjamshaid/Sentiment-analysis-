# filename: app/routes/google_check.py

from fastapi import APIRouter, HTTPException, Query
import httpx
import os
import logging

logger = logging.getLogger("app.google_check")

router = APIRouter()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # Make sure this is set in Railway/Env

@router.get("/autocomplete")
async def google_autocomplete(query: str = Query(..., min_length=1)):
    """
    Call Google Places Autocomplete API to fetch suggestions for a company name.
    """
    if not GOOGLE_API_KEY:
        logger.error("🛑 GOOGLE_API_KEY not set in environment")
        raise HTTPException(status_code=500, detail="Google API Key not configured")

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": query,
        "key": GOOGLE_API_KEY,
        "types": "establishment",
        "components": "country:pk"  # restrict to Pakistan, change if needed
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            predictions = data.get("predictions", [])
            return {"predictions": predictions}

    except httpx.HTTPStatusError as e:
        logger.error("❌ Google API returned error %s: %s", e.response.status_code, e.response.text)
        raise HTTPException(status_code=e.response.status_code, detail="Google API error")
    except Exception as e:
        logger.error("🚨 Google Autocomplete failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Google Autocomplete failed")
