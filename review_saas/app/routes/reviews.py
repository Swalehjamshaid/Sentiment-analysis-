# filename: app/routes/reviews.py

from __future__ import annotations

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import httpx
from fastapi import APIRouter, Query, HTTPException

router = APIRouter()

logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")


# ---------------------------------------------------------
# Simple sentiment analyzer
# ---------------------------------------------------------

POSITIVE_WORDS = {
    "good","great","excellent","amazing","awesome","love",
    "nice","perfect","friendly","best","happy","fast","clean"
}

NEGATIVE_WORDS = {
    "bad","terrible","worst","slow","dirty","hate",
    "poor","awful","disappointed","problem","issue"
}


def sentiment_score(text: str) -> int:
    if not text:
        return 0

    text = text.lower()

    score = 0

    for word in POSITIVE_WORDS:
        if word in text:
            score += 1

    for word in NEGATIVE_WORDS:
        if word in text:
            score -= 1

    if score > 0:
        return 1
    if score < 0:
        return -1

    return 0


# ---------------------------------------------------------
# GOOGLE AUTOCOMPLETE PROXY
# ---------------------------------------------------------

@router.get("/api/google_autocomplete")
async def google_autocomplete(input: str):

    if not GOOGLE_API_KEY:
        raise HTTPException(500, "Google API key missing")

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"

    params = {
        "input": input,
        "key": GOOGLE_API_KEY
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)

    data = r.json()

    return {
        "predictions": data.get("predictions", [])
    }


# ---------------------------------------------------------
# GOOGLE PLACE DETAILS PROXY
# ---------------------------------------------------------

@router.get("/api/google/place/details")
async def google_place_details(place_id: str):

    if not GOOGLE_API_KEY:
        raise HTTPException(500, "Google API key missing")

    url = "https://maps.googleapis.com/maps/api/place/details/json"

    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,reviews,rating",
        "key": GOOGLE_API_KEY
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)

    data = r.json()

    result = data.get("result", {})

    return {
        "name": result.get("name"),
        "address": result.get("formatted_address"),
        "rating": result.get("rating"),
        "reviews": result.get("reviews", [])
    }


# ---------------------------------------------------------
# MAIN REVIEWS API
# ---------------------------------------------------------

@router.get("/api/reviews")
async def get_reviews(
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50
):

    """
    Returns processed review feed for dashboard
    """

    # Normally you would fetch place_id from DB using company_id
    # Here we assume place_id is same as company_id for demo
    place_id = str(company_id)

    if not GOOGLE_API_KEY:
        raise HTTPException(500, "Google API key missing")

    url = "https://maps.googleapis.com/maps/api/place/details/json"

    params = {
        "place_id": place_id,
        "fields": "name,reviews",
        "key": GOOGLE_API_KEY
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)

    data = r.json()

    reviews = data.get("result", {}).get("reviews", [])

    processed: List[Dict[str, Any]] = []

    for r in reviews[:limit]:

        text = r.get("text", "")

        score = sentiment_score(text)

        ts = r.get("time")

        if ts:
            dt = datetime.fromtimestamp(ts)
            review_time = dt.strftime("%Y-%m-%d")
        else:
            review_time = ""

        processed.append({
            "author_name": r.get("author_name"),
            "rating": r.get("rating"),
            "sentiment_score": score,
            "review_time": review_time,
            "text": text
        })

    # Optional filtering
    if start:
        processed = [
            r for r in processed
            if r["review_time"] >= start
        ]

    if end:
        processed = [
            r for r in processed
            if r["review_time"] <= end
        ]

    return {
        "feed": processed
    }
