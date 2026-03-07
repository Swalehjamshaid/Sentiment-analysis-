# File: review_saas/app/services/sentiment.py
from __future__ import annotations
from typing import Dict, List, Optional
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
    Analyzes a single review for overall sentiment and aspects.
    Returns a dict with score, label, complaint/praise flags, and aspect scores.
    """
    if not text:
        return {
            "score": 0.0,
            "label": "Neutral",
            "is_complaint": False,
            "is_praise": False,
            "aspects": {aspect: None for aspect in ASPECT_KEYWORDS}
        }

    compound = float(_analyzer.polarity_scores(text)['compound'])
    text_lower = text.lower()

    # Overall sentiment label
    sentiment_label = label(compound)

    # Complaint / Praise determination
    is_complaint = compound <= -0.25
    is_praise = compound >= 0.6

    # Aspect sentiment extraction
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

def label(compound: float) -> str:
    """
    Converts compound score to human-readable label.
    """
    if compound >= 0.05:
        return "Positive"
    if compound <= -0.05:
        return "Negative"
    return "Neutral"

def score(text: str) -> float:
    """
    Returns the compound sentiment score of the text.
    """
    if not text:
        return 0.0
    return float(_analyzer.polarity_scores(text)['compound'])

def summarize_reviews(reviews: List[str]) -> Dict:
    """
    Aggregate a list of reviews into an executive summary for the dashboard.
    Returns overall sentiment, complaints, praises, aspect averages, and recommendations.
    """
    if not reviews:
        return {
            "overall_score": 0.0,
            "overall_label": "Neutral",
            "total_reviews": 0,
            "total_complaints": 0,
            "total_praises": 0,
            "aspects": {aspect: None for aspect in ASPECT_KEYWORDS},
            "recommendations": []
        }

    total_score = 0.0
    total_complaints = 0
    total_praises = 0
    aspect_totals = {aspect: [] for aspect in ASPECT_KEYWORDS}

    for review in reviews:
        result = analyze_full_review(review)
        total_score += result["score"]
        if result["is_complaint"]:
            total_complaints += 1
        if result["is_praise"]:
            total_praises += 1

        for aspect, score_value in result["aspects"].items():
            if score_value is not None:
                aspect_totals[aspect].append(score_value)

    # Average calculations
    total_reviews = len(reviews)
    overall_score = total_score / total_reviews
    aspect_averages = {}
    for aspect, scores in aspect_totals.items():
        if scores:
            aspect_averages[aspect] = sum(scores) / len(scores)
        else:
            aspect_averages[aspect] = None

    # Generate recommendation summary based on aspects
    recommendations = []
    for aspect, avg_score in aspect_averages.items():
        if avg_score is not None:
            if avg_score <= -0.25:
                recommendations.append(f"Improve {aspect} immediately.")
            elif avg_score >= 0.5:
                recommendations.append(f"{aspect.capitalize()} is performing well.")
            else:
                recommendations.append(f"{aspect.capitalize()} is okay, can be improved.")

    return {
        "overall_score": round(overall_score, 3),
        "overall_label": label(overall_score),
        "total_reviews": total_reviews,
        "total_complaints": total_complaints,
        "total_praises": total_praises,
        "aspects": {k: round(v, 3) if v is not None else None for k, v in aspect_averages.items()},
        "recommendations": recommendations
    }
