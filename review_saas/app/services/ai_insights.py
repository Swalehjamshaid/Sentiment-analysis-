# FILE: app/services/ai_insights.py
from __future__ import annotations
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Iterable
from collections import Counter, defaultdict

import numpy as np
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Requirement #24: Multi-Language Support
try:
    from langdetect import detect, DetectorFactory
    DetectorFactory.seed = 0
except ImportError:
    def detect(text): return "en"

logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()

# ─────────────────────────────────────────────────────────────
# 1. Intelligence Lexicons (#4, #5, #6)
# ─────────────────────────────────────────────────────────────

# Requirement #4: Emotion Detection Layer
EMOTION_LEXICON = {
    "Satisfaction": ["happy", "great", "excellent", "perfect", "pleased", "satisfied"],
    "Frustration": ["wait", "slow", "annoyed", "useless", "ignore", "difficult", "frustrating"],
    "Anger": ["rude", "terrible", "worst", "disgusting", "hate", "angry", "scam"],
    "Excitement": ["amazing", "awesome", "fantastic", "best", "wow", "love"],
    "Disappointment": ["expected", "better", "failed", "unfortunate", "sadly", "disappointed"]
}

# Requirement #5: Aspect-Based Sentiment Analysis
ASPECT_LEXICON = {
    "Service": ["staff", "service", "waiter", "manager", "behavior", "professional", "friendly"],
    "Price": ["cost", "price", "expensive", "cheap", "value", "bill", "money"],
    "Quality": ["taste", "fresh", "quality", "clean", "dirty", "food", "product"],
    "Speed": ["fast", "slow", "delay", "quick", "minutes", "hour", "delivery"]
}

# ─────────────────────────────────────────────────────────────
# 2. Individual Review Intelligence (#3, #4, #5, #24)
# ─────────────────────────────────────────────────────────────

def get_intelligence(text: str, rating: Optional[float]) -> Dict[str, Any]:
    """
    Requirements #3, #4, #5, #24: The core NLP engine.
    Analyzes raw text to extract sentiment, emotions, and business aspects.
    """
    if not text or len(text.strip()) < 3:
        # Fallback to rating-based sentiment if text is missing
        cat = "Positive" if (rating or 0) >= 4 else "Negative" if (rating or 0) <= 2 else "Neutral"
        return {"sentiment": cat, "confidence": 0.5, "emotion": "Neutral", "aspects": {}, "lang": "en"}

    # #24: Multi-Language Support
    try: lang = detect(text)
    except: lang = "en"

    # #3: Advanced Sentiment Classification
    vs = analyzer.polarity_scores(text)
    compound = vs['compound']
    sentiment = "Positive" if compound >= 0.05 else "Negative" if compound <= -0.05 else "Neutral"
    
    t_lower = text.lower()

    # #4: Emotion Detection Layer
    emotion = "Neutral"
    for emo, keywords in EMOTION_LEXICON.items():
        if any(k in t_lower for k in keywords):
            emotion = emo
            break

    # #5: Aspect-Based Analysis
    aspects = {asp: sentiment for asp, kws in ASPECT_LEXICON.items() if any(k in t_lower for k in kws)}

    return {
        "sentiment": sentiment,
        "confidence": round(abs(compound), 2),
        "emotion": emotion,
        "aspects": aspects,
        "lang": lang
    }

# ─────────────────────────────────────────────────────────────
# 3. Aggregate Dashboard Analytics (#7, #9, #10, #20, #21, #27)
# ─────────────────────────────────────────────────────────────

def analyze_reviews(reviews: Iterable[Any], company: Any = None, start: Optional[datetime] = None, end: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Requirement #20: Executive Summary View.
    Requirement #21: Predictive Insights.
    Requirement #27: Anomaly Detection.
    """
    # Use Adapter to avoid circular imports with app.models
    simplified = [SimpleReview.from_any(r) for r in reviews]
    
    # #8: Custom Date Range Filtering
    if start and end:
        simplified = [r for r in simplified if r.review_date and start <= r.review_date <= end]

    if not simplified:
        return {"status": "Empty", "metrics": {"total_volume": 0}, "executive_summary": {"health_score": 0}}

    ratings, sentiments, emotions = [], Counter(), Counter()
    aspect_scores = defaultdict(list)
    
    for r in simplified:
        intel = get_intelligence(r.text, r.rating)
        sentiments[intel['sentiment']] += 1
        emotions[intel['emotion']] += 1
        if r.rating: ratings.append(r.rating)
        for asp, sent in intel['aspects'].items():
            aspect_scores[asp].append(1 if sent == "Positive" else -1)

    total = len(simplified)
    avg_rating = np.mean(ratings) if ratings else 0.0

    # #21: Predictive Insights (Linear Regression for Trend Forecasting)
    prediction = "Stable"
    if len(ratings) > 5:
        slope = np.polyfit(range(len(ratings)), ratings, 1)[0]
        prediction = "Improving" if slope > 0.02 else "Declining" if slope < -0.02 else "Stable"

    # #27: Anomaly Detection (Sudden Rating Drops)
    anomaly = False
    if len(ratings) > 8:
        recent_avg = np.mean(ratings[-3:])
        if recent_avg < (avg_rating - 1.0):
            anomaly = True

    # #10: Correlation Analysis (Sentiment vs Stars)
    # Checks if Positive Sentiment matches High Star Ratings
    mismatches = sum(1 for r in simplified if r.rating <= 2 and get_intelligence(r.text, r.rating)['sentiment'] == "Positive")

    return {
        "avg_rating": round(avg_rating, 2),
        "total_volume": total,
        "executive_summary": { # #20
            "health_score": round((sentiments["Positive"] / total) * 100, 1) if total > 0 else 0,
            "risk_level": "High" if anomaly or prediction == "Declining" else "Low",
            "predictive_signal": prediction,
            "anomaly_detected": anomaly,
            "status": "Action Required" if anomaly else "Optimal"
        },
        "visuals": {
            "emotion_map": dict(emotions), # #4
            "aspect_performance": {k: round(np.mean(v) * 100, 1) for k, v in aspect_scores.items()}, # #5
            "rating_distribution": dict(Counter([int(r.rating) for r in simplified if r.rating])) # #9
        },
        "intelligence_metrics": {
            "mismatch_count": mismatches, # #10 Correlation
            "top_keywords": Counter(" ".join([r.text for r in simplified if r.text]).lower().split()).most_common(10) # #6
        }
    }

def hour_heatmap(reviews: Iterable[Any]) -> Dict[str, Any]:
    """Requirement #7: Sentiment Trend Visualization (Hourly)."""
    hours = [0] * 24
    for r in reviews:
        # Standardize to offset-aware for Python 3.13 compatibility
        dt = getattr(r, 'review_date', None)
        if dt:
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            hours[dt.hour] += 1
    return {"labels": [f"{h}:00" for h in range(24)], "data": hours}

# ─────────────────────────────────────────────────────────────
# 4. Scalable Data Adapter (#30)
# ─────────────────────────────────────────────────────────────

@dataclass
class SimpleReview:
    """Requirement #30: Adapter to handle high volumes and multi-source data."""
    rating: Optional[float]
    text: Optional[str]
    review_date: Optional[datetime]
    source: str = "google"

    @classmethod
    def from_any(cls, obj: Any) -> "SimpleReview":
        # Extracts data from any object (Google API dict or SQL model)
        dt = getattr(obj, "review_date", None)
        if dt and isinstance(dt, datetime) and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
            
        return cls(
            rating=float(getattr(obj, "rating", 0) or 0),
            text=getattr(obj, "text", ""),
            review_date=dt,
            source=getattr(obj, "source_type", "google")
        )
