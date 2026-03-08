# File: review_saas/app/services/outscraper_client.py
from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

class OutscraperClient:
    """
    Minimal Outscraper client for Google Maps reviews.
    Requires env OUTSCRAPER_API_KEY.
    Contracts with Outscraper's REST API and returns {"reviews":[...]} to the caller.
    """

    BASE_URL = os.getenv("OUTSCRAPER_BASE_URL", "https://api.app.outscraper.com")

    def __init__(self, api_key: Optional[str] = None, timeout: int = 60, retries: int = 3, backoff: float = 1.6):
        self.api_key = api_key or os.getenv("OUTSCRAPER_API_KEY")
        if not self.api_key:
            raise RuntimeError("OUTSCRAPER_API_KEY not configured")
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-KEY": self.api_key,
            "Accept": "application/json"
        })

    def _request(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        last_err = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    # rate limited; simple backoff
                    sleep_for = self.backoff ** attempt
                    log.warning("Outscraper rate-limited (429). Sleeping %.1fs (attempt %s/%s)", sleep_for, attempt, self.retries)
                    time.sleep(sleep_for)
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_err = e
                sleep_for = self.backoff ** attempt
                log.warning("Outscraper request failed (attempt %s/%s): %s. Sleeping %.1fs", attempt, self.retries, e, sleep_for)
                time.sleep(sleep_for)
        raise last_err or RuntimeError("Outscraper request failed")

    def get_reviews(self, place_id: str, limit: int, offset: int, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns {"reviews": [ ...mapped reviews... ]}.

        Map Outscraper fields to the generic fields your service expects:
          review_id, author_name, rating, text, time (unix ts), title, helpful_votes, platform, competitor_name
        """
        # NOTE: Adjust endpoint and parameters according to your Outscraper account docs.
        # Many accounts support /maps/reviews with placeId; some use different param names.
        url = f"{self.BASE_URL}/maps/reviews"
        params: Dict[str, Any] = {
            "placeId": place_id,      # sometimes 'place_id' works; prefer 'placeId'
            "limit": limit,
            "offset": offset,
        }

        # Optional tweaks a caller can pass: language, reviewsSort, region, etc.
        if "language" in kwargs: params["language"] = kwargs["language"]
        if "sort" in kwargs: params["reviewsSort"] = kwargs["sort"]  # e.g., "newest", "highest_rating"
        if "region" in kwargs: params["region"] = kwargs["region"]

        data = self._request(url, params=params)

        # Outscraper can return nested shapes. Commonly:
        # { "data": [ { "reviews": [ {...}, ... ] } ] }  or { "reviews": [ ... ] }
        raw_reviews: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            if "reviews" in data and isinstance(data["reviews"], list):
                raw_reviews = data["reviews"]
            elif "data" in data and isinstance(data["data"], list) and data["data"]:
                first = data["data"][0]
                if isinstance(first, dict) and isinstance(first.get("reviews"), list):
                    raw_reviews = first["reviews"]

        # Map a few common Outscraper fields to your generic expected keys:
        mapped: List[Dict[str, Any]] = []
        for r in raw_reviews:
            # Try best-effort mapping (your service still has a robust mapper)
            mapped.append({
                "review_id": r.get("reviewId") or r.get("review_id") or r.get("id"),
                "author_name": r.get("authorName") or r.get("author") or r.get("name"),
                "rating": r.get("rating"),
                "text": r.get("text") or r.get("reviewText") or r.get("content"),
                # prefer epoch seconds if available; otherwise pass raw, service can coerce
                "time": r.get("timestamp") or r.get("time") or r.get("date") or r.get("publishedAt"),
                "title": r.get("title"),
                "helpful_votes": r.get("likesCount") or r.get("thumbsUpCount") or r.get("helpfulVotes"),
                "platform": "Google",
                # If Outscraper includes business name in the response:
                "place_name": r.get("placeName") or r.get("locationName"),
            })

        return {"reviews": mapped}
