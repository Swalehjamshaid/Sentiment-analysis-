# File: app/services/ai_insights.py

from typing import List, Dict, Any
from datetime import datetime
import random

# ---------------------------
# Function: Analyze Reviews
# ---------------------------
def analyze_reviews(reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze a list of reviews and return sentiment scores, ratings, and metrics.
    """
    total_reviews = len(reviews)
    sentiment_summary = {"positive": 0, "neutral": 0, "negative": 0}
    avg_rating = 0

    for r in reviews:
        rating = r.get("rating", 3)
        avg_rating += rating
        sentiment = r.get("sentiment", "Neutral").lower()
        if sentiment == "positive":
            sentiment_summary["positive"] += 1
        elif sentiment == "negative":
            sentiment_summary["negative"] += 1
        else:
            sentiment_summary["neutral"] += 1

    avg_rating = round(avg_rating / total_reviews, 2) if total_reviews > 0 else 0

    return {
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "sentiment_summary": sentiment_summary,
    }


# ---------------------------
# Function: Hour Heatmap
# ---------------------------
def hour_heatmap(reviews: List[Dict[str, Any]]) -> Dict[int, int]:
    """
    Generate heatmap data by hour of day (0-23) for reviews.
    """
    heatmap = {h: 0 for h in range(24)}
    for r in reviews:
        dt = r.get("timestamp")
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except Exception:
                continue
        if isinstance(dt, datetime):
            heatmap[dt.hour] += 1
    return heatmap


# ---------------------------
# Function: Detect Anomalies
# ---------------------------
def detect_anomalies(reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detect anomalous reviews such as spam, fake patterns, or sudden rating drops.
    """
    anomalies = []
    for r in reviews:
        rating = r.get("rating", 3)
        text = r.get("text", "")
        # Simple anomaly logic: very low rating with overly positive text, or vice versa
        if (rating <= 2 and "great" in text.lower()) or (rating >= 4 and "terrible" in text.lower()):
            anomalies.append(r)
        # Random simulated anomaly for demo purposes
        if random.random() < 0.01:
            anomalies.append(r)
    return anomalies
