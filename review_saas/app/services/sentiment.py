# review_saas/app/services/sentiment.py
import re
from langdetect import detect, LangDetectException

def stars_to_category(rating: int) -> str:
    if rating >= 4:
        return 'positive'
    if rating == 3:
        return 'neutral'
    return 'negative'

def analyze_text(text: str) -> tuple[str, float, list[str], str]:
    t = (text or "").strip()
    lang = 'und'
    try:
        lang = detect(t) if t else 'und'
    except LangDetectException:
        lang = 'und'
    pos = len(re.findall(r"(great|good|excellent|love|amazing|best)", t, re.I))
    neg = len(re.findall(r"(bad|poor|terrible|hate|awful|worst)", t, re.I))
    score = max(0.0, min(1.0, 0.5 + 0.15*(pos-neg)))
    cat = 'positive' if score > 0.6 else ('negative' if score < 0.4 else 'neutral')
    keywords = re.findall(r"\w{6,}", t)[:10]
    return cat, score, keywords, lang
