# filename: app/services/sentiment.py
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

def star_to_category(rating: int) -> str:
    if rating is None:
        return 'Neutral'
    if rating >= 4:
        return 'Positive'
    if rating == 3:
        return 'Neutral'
    return 'Negative'

def text_sentiment(text: str):
    if not text:
        return {'compound': 0.0}
    return analyzer.polarity_scores(text)
