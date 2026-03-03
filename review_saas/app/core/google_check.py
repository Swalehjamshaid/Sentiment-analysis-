# File: /app/app/core/google_check.py
from __future__ import annotations
import httpx
from fastapi import APIRouter, HTTPException

# Router for Google check endpoints
router = APIRouter()

@router.get("/check-google")
async def check_google():
    """
    File: /app/app/core/google_check.py
    Endpoint to check if Google is reachable.
    Returns JSON response with status.
    """
    url = "https://www.google.com"

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(url)
            if response.status_code == 200:
                return {"status": "success", "message": "Google is reachable"}
            else:
                return {
                    "status": "fail",
                    "message": f"Google returned status code {response.status_code}",
                }
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Error connecting to Google: {str(e)}"
            )
