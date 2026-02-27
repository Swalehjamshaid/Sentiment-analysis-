# filename: review_saas/app/services/google_api.py
"""
Google API Service (Dual Mode)
- Mode A: Google My Business (service account JSON via GOOGLE_APPLICATION_CREDENTIALS)
- Mode B: Google Places API (API key via GOOGLE_PLACES_API_KEY)
Provides:
  - health_check(place_id=None) -> dict
  - get_place_details(place_id) -> dict
  - get_reviews(place_id=...) -> List[dict]  (normalized)
  - fetch_reviews_async(place_id=...) -> async wrapper
Notes:
  * Places API 'reviews' via Place Details are limited/sampled.
  * My Business Business Calls discovery name kept from your legacy code, but
    reviews often require the Google Business Profile API with different discovery doc.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("review_saas.google_api")

# Optional dependencies — guard imports so we never crash on startup
try:
    # Google Business (service account)
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except Exception:  # pragma: no cover
    service_account = None  # type: ignore
    build = None  # type: ignore

try:
    # Google Places API via python client
    import googlemaps  # used elsewhere in your codebase too
except Exception:  # pragma: no cover
    googlemaps = None  # type: ignore


class GoogleAPIService:
    """
    Dual-mode Google API facade:
      - If GOOGLE_APPLICATION_CREDENTIALS exists → initialize service account flow.
      - Else if GOOGLE_PLACES_API_KEY exists → initialize Places client.
      - Else → limited mode (no API calls).

    Public methods prefer Places 'place_id' workflow since your frontend uses Place Autocomplete.
    """

    def __init__(self, credentials_json_path: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.service = None             # My Business service client (if any)
        self.gmaps = None               # googlemaps.Client (if any)
        self.provider = "none"

        # 1) Try service account (Google Business)
        path = credentials_json_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        if path and os.path.exists(path) and service_account and build:
            try:
                creds = service_account.Credentials.from_service_account_file(
                    path,
                    scopes=["https://www.googleapis.com/auth/business.manage"]
                )
                # Legacy discovery used in your older file; some review endpoints are in
                # Google Business Profile API (different discovery). We keep this to remain
                # backward-compatible and non-crashing; you can swap the discovery if needed.
                self.service = build("mybusinessbusinesscalls", "v1", credentials=creds)
                self.provider = "business_service_account"
                logger.info("Google Business service initialized (service account).")
            except Exception as e:
                logger.warning("Service account init failed: %s", e)

        # 2) Try Places API (API key)
        key = api_key or os.getenv("GOOGLE_PLACES_API_KEY", "")
        if not self.service and key:
            if googlemaps is None:
                logger.warning("googlemaps package not available; cannot use Places API.")
            else:
                try:
                    self.gmaps = googlemaps.Client(key=key)
                    self.provider = "places_api_key"
                    logger.info("Google Places client initialized (API key).")
                except Exception as e:
                    logger.warning("Places API init failed: %s", e)

        # 3) Limited mode
        if not self.service and not self.gmaps:
            logger.warning(
                "GoogleAPIService running in LIMITED mode: "
                "set GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_PLACES_API_KEY."
            )

    # ---------------------------------------------------------------------
    # Health
    # ---------------------------------------------------------------------
    def health_check(self, place_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns a normalized health object for dashboards.
        When in Places mode and place_id provided, attempts a lightweight call.
        """
        status = "unavailable"
        healthy = False
        reason = "no_credentials"
        provider = self.provider

        try:
            if self.provider == "business_service_account" and self.service:
                # We don't know the actual account endpoints available here;
                # a simple sanity presence check is all we can assert.
                status = "ok"
                healthy = True
                reason = "service_initialized"

            elif self.provider == "places_api_key" and self.gmaps:
                if place_id:
                    # Lightweight ping: request just 'name' field
                    res = self._gmaps_place_details(place_id, fields=["name"])
                    healthy = bool(res.get("result"))
                    status = "ok" if healthy else "empty"
                    reason = "places_details_ok" if healthy else "not_found"
                else:
                    status = "ok"
                    healthy = True
                    reason = "api_key_available"

            else:
                status = "unavailable"
                healthy = False
                reason = "no_provider"
        except Exception as e:
            status = "error"
            healthy = False
            reason = f"exception:{e}"

        return {
            "status": status,
            "healthy": healthy,
            "provider": provider,
            "reason": reason,
        }

    # ---------------------------------------------------------------------
    # Place details (Places API)
    # ---------------------------------------------------------------------
    def get_place_details(self, place_id: str) -> Dict[str, Any]:
        """
        Returns normalized place details if Places API is available.
        If only Business service is available, returns minimal.
        """
        if not place_id:
            return {}

        if self.gmaps:
            try:
                details = self._gmaps_place_details(place_id)
                result = details.get("result", {}) if isinstance(details, dict) else {}
                return self._normalize_place_details(result)
            except Exception as e:
                logger.warning("get_place_details failed: %s", e)
                return {}

        # Service account path: no direct place details; return minimal
        return {"place_id": place_id}

    # ---------------------------------------------------------------------
    # Reviews (Place Details → reviews sample)
    # ---------------------------------------------------------------------
    def get_reviews(
        self,
        place_id: Optional[str] = None,
        account_id: Optional[str] = None,
        location_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Universal reviews getter:
          - If place_id and Places API is configured → return Place Details reviews (sampled).
          - Else if Business service is configured and account/location are provided → try Business call stub.
          - Else → [].
        """
        # Prefer Places workflow because your frontend uses place_id
        if place_id and self.gmaps:
            try:
                details = self._gmaps_place_details(place_id, fields=["review", "name", "rating", "user_ratings_total"])
                result = details.get("result", {}) if isinstance(details, dict) else {}
                reviews = result.get("reviews", []) or []
                return [self._normalize_place_review(r, place_id) for r in reviews]
            except Exception as e:
                logger.warning("Places get_reviews failed: %s", e)
                return []

        # Fallback to Business (legacy behavior from old file)
        if self.service and account_id and location_id:
            try:
                # The discovery used in your legacy code may not expose reviews directly;
                # this returns [] safely if not supported.
                resp = (
                    self.service.accounts()
                    .locations()
                    .reviews()
                    .list(parent=f"accounts/{account_id}/locations/{location_id}")
                    .execute()
                )
                reviews = resp.get("reviews", []) or []
                # Normalize to a unified review shape
                return [self._normalize_business_review(r, account_id, location_id) for r in reviews]
            except Exception as e:
                logger.warning("Business get_reviews failed: %s", e)
                return []

        return []

    # Async wrapper (used by some parts of your codebase)
    async def fetch_reviews_async(self, place_id: str) -> Dict[str, Any]:
        """
        Async-friendly wrapper that returns {'reviews': [...], 'fetched': int}
        """
        try:
            reviews = self.get_reviews(place_id=place_id)
            return {"reviews": reviews, "fetched": len(reviews)}
        except Exception as e:
            logger.warning("fetch_reviews_async failed: %s", e)
            return {"reviews": [], "fetched": 0, "error": str(e)}

    # ---------------------------------------------------------------------
    # Internals (Places)
    # ---------------------------------------------------------------------
    def _gmaps_place_details(self, place_id: str, fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Calls googlemaps Place Details API safely.
        """
        if not self.gmaps:
            return {}
        try:
            return self.gmaps.place(
                place_id=place_id,
                fields=fields or [
                    "place_id",
                    "name",
                    "formatted_address",
                    "address_components",
                    "geometry",
                    "url",
                    "website",
                    "formatted_phone_number",
                    "international_phone_number",
                    "rating",
                    "user_ratings_total",
                    "types",
                    "review",
                ],
            )
        except Exception as e:
            logger.warning("gmaps.place failed: %s", e)
            return {}

    # ---------------------------------------------------------------------
    # Normalizers (unified to your Review & Company schemas)
    # ---------------------------------------------------------------------
    def _normalize_place_details(self, r: Dict[str, Any]) -> Dict[str, Any]:
        def _by_type(t: str) -> str:
            comps = r.get("address_components") or []
            for c in comps:
                if t in (c.get("types") or []):
                    return c.get("long_name") or ""
            return ""

        geom = r.get("geometry") or {}
        loc = geom.get("location") or {}
        url = r.get("url") or ""
        return {
            "place_id": r.get("place_id"),
            "name": r.get("name"),
            "address": r.get("formatted_address"),
            "city": _by_type("locality") or _by_type("sublocality"),
            "state": _by_type("administrative_area_level_1"),
            "postal_code": _by_type("postal_code"),
            "country": _by_type("country"),
            "latitude": loc.get("lat"),
            "longitude": loc.get("lng"),
            "phone": r.get("international_phone_number") or r.get("formatted_phone_number"),
            "website": r.get("website"),
            "google_url": url,
            "rating": r.get("rating"),
            "user_ratings_total": r.get("user_ratings_total"),
            "types": ",".join(r.get("types") or []),
        }

    def _normalize_place_review(self, rv: Dict[str, Any], place_id: str) -> Dict[str, Any]:
        ts = rv.get("time")  # seconds since epoch (UTC)
        dt_iso = None
        if ts is not None:
            try:
                dt_iso = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
            except Exception:
                dt_iso = None

        return {
            "source": "google",
            "external_id": f"gplace:{place_id}:{rv.get('author_name','')}:{rv.get('time','')}",
            "reviewer_name": rv.get("author_name"),
            "reviewer_avatar": rv.get("profile_photo_url"),
            "rating": rv.get("rating"),
            "text": rv.get("text"),
            "review_date": dt_iso,  # ISO for easy serialization
            "language": rv.get("language", None),
            # Optional sentiment placeholders; your AI pipeline can populate later
            "sentiment_category": None,
            "sentiment_score": None,
            "sentiment_confidence": None,
        }

    def _normalize_business_review(self, rv: Dict[str, Any], account_id: str, location_id: str) -> Dict[str, Any]:
        # This depends on the actual payload shape of the Business API you use.
        # Provide conservative keys to remain compatible with your Review model.
        author = (rv.get("reviewer") or {}).get("displayName")
        rating = rv.get("starRating")
        comment = rv.get("comment")
        update_time = rv.get("updateTime") or rv.get("createTime")

        return {
            "source": "google_business",
            "external_id": f"gbiz:{account_id}:{location_id}:{rv.get('name','')}",
            "reviewer_name": author,
            "reviewer_avatar": None,
            "rating": rating,
            "text": comment,
            "review_date": update_time,  # already ISO-like per API
            "language": None,
            "sentiment_category": None,
            "sentiment_score": None,
            "sentiment_confidence": None,
        }


# Factory (kept compatible with your older imports)
def get_google_api_service(credentials_json_path: str | None = None) -> GoogleAPIService:
    """
    Creates a GoogleAPIService using env:
      - GOOGLE_APPLICATION_CREDENTIALS → service account (Business)
      - GOOGLE_PLACES_API_KEY → Places API key
    """
    path = credentials_json_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    return GoogleAPIService(credentials_json_path=path or None, api_key=api_key or None)
