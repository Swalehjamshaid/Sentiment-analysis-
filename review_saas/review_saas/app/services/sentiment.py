
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from langdetect import detect, LangDetectException
import re, json

analyzer = SentimentIntensityAnalyzer()


def star_based_category(stars: int | None):
    if stars is None:
        return None
    if stars >= 4:
        return 'Positive'
    if stars == 3:
        return 'Neutral'
    return 'Negative'


def clean_text(text: str | None) -> str:
    if not text:
        return ''
    t = re.sub(r'<[^>]+>', ' ', text)  # strip HTML
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def sentiment_score(text: str) -> float:
    if not text:
        return 0.0
    try:
        lang = detect(text)
    except LangDetectException:
        lang = 'en'
    # VADER is tuned for English; for non-English, we still return a heuristic
    s = analyzer.polarity_scores(text)
    return (s['compound'] + 1) / 2  # map -1..1 to 0..1


def detect_keywords(text: str):
    text_l = text.lower()
    keywords = []
    positive = ['great', 'excellent', 'amazing', 'friendly', 'fast', 'clean', 'helpful']
    negative = ['bad', 'poor', 'rude', 'slow', 'dirty', 'unhelpful', 'expensive']
    service = ['service', 'staff', 'food', 'delivery', 'price', 'quality']
    for kw in positive + negative + service:
        if kw in text_l:
            keywords.append(kw)
    return json.dumps(list(set(keywords)))
