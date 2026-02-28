# filename: app/services/google_client.py
from ..core.config import Settings
import googlemaps

class GoogleClient:
    def __init__(self):
        self.api_key = Settings().google_maps_api_key
        self.client = googlemaps.Client(key=self.api_key) if self.api_key else None

    def validate_place_id(self, place_id: str) -> bool:
        if not self.client or not place_id:
            return False
        try:
            details = self.client.place(place_id=place_id)
            return details and details.get('status') == 'OK'
        except Exception:
            return False
