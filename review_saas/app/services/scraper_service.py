# filename: app/services/scraper.py
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from textblob import TextBlob

analyzer = SentimentIntensityAnalyzer()

async def fetch_reviews(place_id: str, limit: int = 300, skip: int = 0) -> List[Dict[str, Any]]:
    """
    Dummy Python-based review generator to simulate Google Reviews.
    Returns realistic reviews with sentiment analysis using Python libraries.
    """
    dummy_texts = [
        "Excellent service and friendly staff.",
        "Average experience, nothing special.",
        "Very poor service, will not return.",
        "Great ambiance, highly recommend!",
        "Okay experience, could be better.",
        "Terrible food, extremely disappointed.",
        "Loved it, five stars!",
        "Not bad, but not great either."
    ]

    reviews_list: List[Dict[str, Any]] = []

    for i in range(skip, skip + limit):
        text = random.choice(dummy_texts)
        rating = random.randint(1, 5)

        # Sentiment using Vader
        vader_score = analyzer.polarity_scores(text)["compound"]
        # Sentiment using TextBlob
        tb_score = TextBlob(text).sentiment.polarity
        # Combine for simple score
        score = (vader_score + tb_score) / 2

        # Determine label
        if score > 0.05:
            label = "Positive"
        elif score < -0.05:
            label = "Negative"
        else:
            label = "Neutral"

        reviews_list.append({
            "review_id": f"{place_id}_review_{i+1}",
            "author_name": f"User_{i+1}",
            "rating": rating,
            "text": text,
            "google_review_time": (datetime.utcnow() - timedelta(days=i)).isoformat(),
            "sentiment_score": score,
            "sentiment_label": label
        })

    return reviews_list
