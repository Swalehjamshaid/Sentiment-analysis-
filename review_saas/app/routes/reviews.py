
# filename: app/routes/reviews.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from app.core.config import settings
from app.services.google_reviews import fetch_place_details

router = APIRouter(tags=['google'])

@router.get('/google/health')
async def google_health():
    if not settings.GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=400, detail='GOOGLE_MAPS_API_KEY missing')
    try:
        details = fetch_place_details('ChIJ2eUgeAK6j4ARbn5u_wAGqWA')
        return {"ok": True, "status": details.get('status'), "has_result": bool(details.get('result'))}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Google API error: {exc}")
