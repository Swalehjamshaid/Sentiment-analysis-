# filename: app/services/google_api.py
from dataclasses import dataclass

@dataclass
class GooglePlacesClient:
    api_key: str
    def autocomplete(self, query: str):
        return {'predictions': []}
