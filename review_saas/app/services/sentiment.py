
# filename: app/services/sentiment.py
from __future__ import annotations
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()

def classify(text: str | None, stars: int | None) -> tuple[str, float]:
    if stars is not None:
        if stars >= 4: return 'Positive', 1.0
        if stars == 3: return 'Neutral', 0.5
        if stars <= 2: return 'Negative', 0.0
    if not text:
        return 'Neutral', 0.5
    s = _analyzer.polarity_scores(text)['compound']
    if s >= 0.3: return 'Positive', s
    if s <= -0.3: return 'Negative', s
    return 'Neutral', s
