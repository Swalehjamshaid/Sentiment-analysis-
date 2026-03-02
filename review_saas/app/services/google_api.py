import requests
from typing import Optional, List, Dict
from datetime import datetime
from app.core.config import settings

class GoogleApiService:
    def __init__(self):
        self.api_key = settings.GOOGLE_PLACES_API_KEY
        self.base_url = "https://maps.googleapis.com/maps/api/place"

    def search_company_by_name(self, company_name: str) -> Optional[Dict]:
        """
        Requirement: Integrate with Google Places API to search companies by name.
        Auto-fills: Name, Address, Phone, Website, and Category.
        """
        endpoint = f"{self.base_url}/findplacefromtext/json"
        params = {
            "input": company_name,
            "inputtype": "textquery",
            "fields": "name,formatted_address,place_id,types,business_status",
            "key": self.api_key
        }
        
        response = requests.get(endpoint, params=params)
        data = response.json()
        
        if data.get("candidates"):
            return data["candidates"][0] # Returns the most relevant match
        return None

    def get_company_details(self, place_id: str) -> Dict:
        """
        Requirement: Auto-fill phone number, website, and business hours.
        Stores the Google Place ID for future API calls.
        """
        endpoint = f"{self.base_url}/details/json"
        params = {
            "place_id": place_id,
            "fields": "name,formatted_address,formatted_phone_number,website,rating,user_ratings_total,opening_hours,reviews",
            "key": self.api_key
        }
        
        response = requests.get(endpoint, params=params)
        return response.json().get("result", {})

    def fetch_reviews_by_date_range(self, place_id: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Requirement: Retrieve all reviews and rating data within the selected date range.
        This fetches the individual reviews for numerical and star-based display.
        """
        details = self.get_company_details(place_id)
        all_reviews = details.get("reviews", [])
        
        filtered_reviews = []
        for review in all_reviews:
            # Google API provides 'time' as a Unix timestamp
            review_date = datetime.fromtimestamp(review["time"])
            
            if start_date <= review_date <= end_date:
                filtered_reviews.append({
                    "reviewer_name": review.get("author_name"),
                    "rating": review.get("rating"),
                    "comment": review.get("text"),
                    "date": review_date.strftime("%Y-%m-%d"),
                    "relative_time": review.get("relative_time_description")
                })
                
        return filtered_reviews

    def calculate_period_analytics(self, reviews: List[Dict]) -> Dict:
        """
        Requirement: Calculate average rating and total number of reviews for the period.
        Supports the 1-star to 5-star breakdown display.
        """
        if not reviews:
            return {"average_rating": 0, "total_reviews": 0, "distribution": {i: 0 for i in range(1, 6)}}

        total_rating = sum(r["rating"] for r in reviews)
        distribution = {i: 0 for i in range(1, 6)}
        
        for r in reviews:
            distribution[r["rating"]] += 1
            
        return {
            "average_rating": round(total_rating / len(reviews), 2),
            "total_reviews": len(reviews),
            "distribution": distribution
        }

google_api_service = GoogleApiService()
