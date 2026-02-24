# review_saas/app/services/ai_insights.py

from collections import Counter, defaultdict
from datetime import datetime
import random

# ---------------------------
# Analyze Reviews
# ---------------------------
def analyze_reviews(reviews: list[dict]) -> dict:
    sentiment_map = {"Positive": 0, "Neutral": 0, "Negative": 0}
    emotion_map = defaultdict(int)
    aspect_performance = defaultdict(list)
    total_volume = len(reviews)
    avg_rating = 0
    response_rate = 0

    for review in reviews:
        sentiment = review.get("sentiment", random.choice(["Positive","Neutral","Negative"]))
        sentiment_map[sentiment] += 1
        emotion = review.get("emotion", random.choice(["Satisfaction","Frustration","Anger","Excitement","Disappointment"]))
        emotion_map[emotion] += 1
        for aspect, score in review.get("aspects", {}).items():
            aspect_performance[aspect].append(score)
        avg_rating += review.get("rating", 0)
        if review.get("response"):
            response_rate += 1

    avg_rating = round(avg_rating / total_volume, 1) if total_volume else 0
    response_rate_pct = f"{round((response_rate/total_volume)*100,1)}%" if total_volume else "0%"
    aspect_avg = {k: round(sum(v)/len(v),1) for k,v in aspect_performance.items()}

    return {
        "sentiment_map": sentiment_map,
        "emotion_map": dict(emotion_map),
        "aspect_performance": aspect_avg,
        "total_volume": total_volume,
        "avg_rating": avg_rating,
        "response_rate": response_rate_pct
    }

# ---------------------------
# Hour Heatmap
# ---------------------------
def hour_heatmap(reviews: list[dict]) -> dict:
    heatmap = {str(i):0 for i in range(24)}
    for review in reviews:
        dt_str = review.get("timestamp")
        if dt_str:
            try:
                dt = datetime.fromisoformat(dt_str)
                heatmap[str(dt.hour)] += 1
            except:
                continue
    return heatmap

# ---------------------------
# Anomaly Detection
# ---------------------------
def detect_anomalies(reviews: list[dict]) -> list[dict]:
    flagged = []
    user_counter = Counter([r.get("reviewer_name","") for r in reviews])
    for review in reviews:
        name = review.get("reviewer_name","")
        rating = review.get("rating",0)
        text = review.get("text","")
        if user_counter[name]>3:
            flagged.append({**review,"reason":"Multiple reviews by same user"})
        elif len(text)<5 or text.lower() in ["good","bad","ok"]:
            flagged.append({**review,"reason":"Low content quality"})
        elif rating==1 and "excellent" in text.lower():
            flagged.append({**review,"reason":"Rating mismatch"})
    return flagged

# ---------------------------
# Forecast Sentiment & Rating (New Function)
# ---------------------------
def forecast_sentiment_and_rating(reviews: list[dict]) -> dict:
    """
    Returns a simple AI-driven forecast of average rating and sentiment trends.
    This is a placeholder: can integrate ML models later.
    """
    analysis = analyze_reviews(reviews)
    # simple trend forecast: assume small positive drift
    forecasted_rating = round(min(5, analysis["avg_rating"] + random.uniform(0, 0.3)), 1)
    forecasted_sentiment = {
        k: min(100, int(v * random.uniform(1.0, 1.1))) for k, v in analysis["sentiment_map"].items()
    }
    return {
        "forecasted_rating": forecasted_rating,
        "forecasted_sentiment": forecasted_sentiment
    }

# ---------------------------
# Wrapper: Get Intelligence
# ---------------------------
def get_intelligence(reviews: list[dict]) -> dict:
    return {
        "analysis": analyze_reviews(reviews),
        "heatmap": hour_heatmap(reviews),
        "anomalies": detect_anomalies(reviews),
        "forecast": forecast_sentiment_and_rating(reviews)
    }
