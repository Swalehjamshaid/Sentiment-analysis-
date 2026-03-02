
# filename: app/services/sentiment.py
from __future__ import annotations
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
_analyzer = SentimentIntensityAnalyzer()

def score(text: str) -> float:
    if not text: return 0.0
    return float(_analyzer.polarity_scores(text)['compound'])

def label(compound: float) -> str:
    if compound >= 0.05: return 'Positive'
    if compound <= -0.05: return 'Negative'
    return 'Neutral'
