# filename: app/core/google_check.py
from googlemaps import Client
from app.core.config import settings
import requests

def verify_google_apis():
    """
    Verifies Google Places, Maps, and Business APIs at startup.
    Prints status to the console.
    """
    try:
        # Google Places API
        gmaps_places = Client(key=settings.GOOGLE_PLACES_API_KEY)
        places_result = gmaps_places.places(query="Haier Lahore")
        if places_result.get("status") != "OK":
            print("⚠️ Google Places API warning:", places_result.get("status"))
        else:
            print("✅ Google Places API is working.")

        # Google Maps API
        gmaps_maps = Client(key=settings.GOOGLE_MAPS_API_KEY)
        maps_result = gmaps_maps.geocode("Lahore, Pakistan")
        if not maps_result:
            print("⚠️ Google Maps API returned empty result")
        else:
            print("✅ Google Maps API is working.")

        # Google Business API
        business_url = (
            f"https://mybusinessbusinessinformation.googleapis.com/v1/locations"
            f"?key={settings.GOOGLE_BUSINESS_API_KEY}"
        )
        resp = requests.get(business_url)
        if resp.status_code != 200:
            print(f"⚠️ Google Business API warning: Status code {resp.status_code}")
        else:
            print("✅ Google Business API is working.")

    except Exception as e:
        print("❌ Google API check failed:", str(e))
