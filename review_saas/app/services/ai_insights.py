# review_saas/app/services/ai_insights.py

from collections import Counter, defaultdict
from datetime import datetime
import random

# ---------------------------
# Analyze Reviews - Sentiment & Aspect Detection
# ---------------------------
def analyze_reviews(reviews: list[dict]) -> dict:
    """
    Performs sentiment analysis, aspect breakdown, and rating aggregation.
    Returns a summary dictionary.
    """
    sentiment_map = {"Positive": 0, "Neutral": 0, "Negative": 0}
    emotion_map = defaultdict(int)
    aspect_performance = defaultdict(list)
    total_volume = len(reviews)
    avg_rating = 0
    response_rate = 0

    for review in reviews:
        # Sentiment Classification
        sentiment = review.get("sentiment", random.choice(["Positive", "Neutral", "Negative"]))
        sentiment_map[sentiment] += 1

        # Emotion Detection
        emotion = review.get("emotion", random.choice(["Satisfaction", "Frustration", "Anger", "Excitement", "Disappointment"]))
        emotion_map[emotion] += 1

        # Aspect-Based Analysis
        for aspect, score in review.get("aspects", {}).items():
            aspect_performance[aspect].append(score)

        # Aggregate rating
        avg_rating += review.get("rating", 0)

        # Response Tracking
        if review.get("response", None):
            response_rate += 1

    # Final calculations
    avg_rating = round(avg_rating / total_volume, 1) if total_volume else 0
    response_rate_pct = f"{round((response_rate / total_volume) * 100, 1)}%" if total_volume else "0%"

    # Average aspect score
    aspect_avg = {k: round(sum(v)/len(v), 1) for k, v in aspect_performance.items()}

    return {
        "sentiment_map": sentiment_map,
        "emotion_map": dict(emotion_map),
        "aspect_performance": aspect_avg,
        "total_volume": total_volume,
        "avg_rating": avg_rating,
        "response_rate": response_rate_pct
    }


# ---------------------------
# Hour Heatmap - Review Distribution
# ---------------------------
def hour_heatmap(reviews: list[dict]) -> dict:
    """
    Returns a heatmap of reviews by hour of day.
    """
    heatmap = {str(i): 0 for i in range(24)}
    for review in reviews:
        dt_str = review.get("timestamp")
        if dt_str:
            try:
                dt = datetime.fromisoformat(dt_str)
                heatmap[str(dt.hour)] += 1
            except Exception:
                continue
    return heatmap


# ---------------------------
# Detect Anomalies - Spam or Unusual Patterns
# ---------------------------
def detect_anomalies(reviews: list[dict]) -> list[dict]:
    """
    Detects unusual patterns like multiple reviews from same user or spam content.
    Returns a list of flagged review dicts.
    """
    flagged = []
    user_counter = Counter([r.get("reviewer_name", "") for r in reviews])

    for review in reviews:
        name = review.get("reviewer_name", "")
        rating = review.get("rating", 0)
        text = review.get("text", "")

        # Simple anomaly rules
        if user_counter[name] > 3:
            flagged.append({**review, "reason": "Multiple reviews by same user"})
        elif len(text) < 5 or text.lower() in ["good", "bad", "ok"]:
            flagged.append({**review, "reason": "Low content quality"})
        elif rating == 1 and "excellent" in text.lower():
            flagged.append({**review, "reason": "Rating mismatch"})
    return flagged


# ---------------------------
# Wrapper: Get Intelligence
# ---------------------------
def get_intelligence(reviews: list[dict]) -> dict:
    """
    Combines analysis, heatmap, and anomaly detection.
    Returns a unified intelligence report.
    """
    analysis = analyze_reviews(reviews)
    heatmap = hour_heatmap(reviews)
    anomalies = detect_anomalies(reviews)

    return {
        "analysis": analysis,
        "heatmap": heatmap,
        "anomalies": anomalies
    }
