from typing import Tuple

def classify_sentiment(star_rating: int | None) -> str:
    if star_rating is None:
        return "Neutral"
    if star_rating >= 4:
        return "Positive"
    if star_rating == 3:
        return "Neutral"
    return "Negative"

# naive keyword extraction (bonus)
POSITIVE_KEYWORDS = ["great","excellent","friendly","clean","fast","recommend","love","amazing","best"]
NEGATIVE_KEYWORDS = ["slow","bad","worst","dirty","late","rude","expensive","poor","terrible","complaint"]

def extract_keywords(text: str | None) -> str:
    if not text:
        return ""
    tokens = [t.strip('.,!?:;"'').lower() for t in text.split()]
    hits = [t for t in tokens if t in POSITIVE_KEYWORDS or t in NEGATIVE_KEYWORDS]
    # return unique keywords
    uniq = []
    for w in hits:
        if w not in uniq:
            uniq.append(w)
    return ", ".join(uniq)