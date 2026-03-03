# filename: app/core/google_check.py
from googlemaps import Client
import requests
from app.core.config import settings

def verify_google_apis():
    """
    Verify that all configured Google APIs are reachable.
    Prints results to the console without blocking app startup.
    """
    try:
        # Google Places API
        gmaps_places = Client(key=settings.GOOGLE_PLACES_API_KEY)
        if gmaps_places.places(query="Haier Lahore").get("results"):
            print("✅ Google Places API is working.")
        else:
            print("⚠️ Google Places API returned empty results.")

        # Google Maps API
        gmaps_maps = Client(key=settings.GOOGLE_MAPS_API_KEY)
        if gmaps_maps.geocode("Lahore, Pakistan"):
            print("✅ Google Maps API is working.")
        else:
            print("⚠️ Google Maps API returned empty results.")

        # Google Business API (REST request)
        business_url = f"https://mybusinessbusinessinformation.googleapis.com/v1/locations?key={settings.GOOGLE_BUSINESS_API_KEY}"
        resp = requests.get(business_url)
        if resp.status_code == 200:
            print("✅ Google Business API is working.")
        else:
            print(f"⚠️ Google Business API returned status {resp.status_code}")

    except Exception as e:
        print(f"❌ Google API check failed: {e}")
