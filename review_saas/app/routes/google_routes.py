# filename: app/app/routes/google_routes.py
from fastapi import APIRouter
from app.core.config import get_settings

router = APIRouter(tags=['google'])

@router.get('/google/health')
def health():
    s = get_settings()
    return {'ok': bool(s.google_maps_api_key or s.google_places_api_key)}

@router.get('/google/sync')
def sync():
    # stubbed
    return {'ok': True, 'message': 'Google sync started'}
