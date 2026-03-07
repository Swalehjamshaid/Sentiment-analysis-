from __future__ import annotations
import re
from typing import Dict, Optional, Tuple
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()

# Keywords for Departmental/Aspect Analysis
ASPECT_KEYWORDS = {
    "rooms": ["room", "bed", "bathroom", "shower", "sleep", "view", "suite"],
    "staff": ["staff", "service", "manager", "reception", "waiter", "host", "behavior"],
    "cleanliness": ["clean", "dirty", "dust", "hygiene", "smell", "fresh", "stain"],
    "value": ["price", "cost", "expensive", "worth", "money", "value", "cheap"],
    "location": ["location", "area", "near", "distance", "transport", "centered", "mall"],
    "food": ["food", "breakfast", "dinner", "restaurant", "buffet", "taste", "chef"]
}

def analyze_full_review(text: str) -> Dict:
    """
    Comprehensive analysis providing all attributes required for the 
    decision-making dashboard.
    """
    if not text:
        return {
            "score": 0.0, "label": "Neutral", "is_complaint": False, 
            "is_praise": False, "aspects": {}
        }

    compound = float(_analyzer.polarity_scores(text)['compound'])
    text_lower = text.lower()

    # 1. Base Sentiment and Label
    sentiment_label = label(compound)

    # 2. Decision Logic: Is it a Complaint or Praise?
    # Logic: Very low sentiment = Complaint; Very high = Praise
    is_complaint = True if compound <= -0.25 else False
    is_praise = True if compound >= 0.6 else False

    # 3. Aspect-Based Sentiment Extraction
    # Scans text for departmental keywords and assigns the review score to that aspect
    aspect_scores = {}
    for aspect, keywords in ASPECT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            aspect_scores[aspect] = compound
        else:
            aspect_scores[aspect] = None

    return {
        "score": compound,
        "label": sentiment_label,
        "is_complaint": is_complaint,
        "is_praise": is_praise,
        "aspects": aspect_scores
    }

def score(text: str) -> float:
    if not text: return 0.0
    return float(_analyzer.polarity_scores(text)['compound'])

def label(compound: float) -> str:
    if compound >= 0.05: return 'Positive'
    if compound <= -0.05: return 'Negative'
    return 'Neutral'
