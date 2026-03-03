# filename: app/core/google_check.py
from googlemaps import Client
from app.core.config import settings
import requests

def verify_google_apis():
    """
    Verify Google Places, Maps, and Business APIs.
    Prints status to console.
    Does NOT block the main application startup.
    """
    try:
        # Google Places API check
        gmaps_places = Client(key=settings.GOOGLE_PLACES_API_KEY)
        places_result = gmaps_places.places(query="Haier Lahore")
        if places_result.get("results"):
            print("✅ Google Places API is working.")
        else:
            print("⚠️ Google Places API returned empty results.")

        # Google Maps API check
        gmaps_maps = Client(key=settings.GOOGLE_MAPS_API_KEY)
        maps_result = gmaps_maps.geocode("Lahore, Pakistan")
        if maps_result:
            print("✅ Google Maps API is working.")
        else:
            print("⚠️ Google Maps API returned empty results.")

        # Google Business API check
        business_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/locations?key={settings.GOOGLE_BUSINESS_API_KEY}"
        resp = requests.get(business_url)
        if resp.status_code == 200:
            print("✅ Google Business API is working.")
        else:
            print(f"⚠️ Google Business API returned status code {resp.status_code}.")

    except Exception as e:
        print(f"❌ Google API check failed: {str(e)}")
