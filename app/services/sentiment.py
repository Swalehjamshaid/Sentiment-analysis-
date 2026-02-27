
import re
try:
    from langdetect import detect, LangDetectException  # type: ignore
except Exception:
    detect = None
    class LangDetectException(Exception):
        pass

def stars_to_category(rating: int) -> str:
    if rating >= 4:
        return 'Positive'
    if rating == 3:
        return 'Neutral'
    return 'Negative'

def analyze_text(text: str):
    t = (text or '').strip()
    lang = 'und'
    if detect and t:
        try:
            lang = detect(t)
        except LangDetectException:
            lang = 'und'
    pos = len(re.findall(r"(great|good|excellent|love|amazing|best)", t, re.I))
    neg = len(re.findall(r"(bad|poor|terrible|hate|awful|worst)", t, re.I))
    score = max(0.0, min(1.0, 0.5 + 0.15*(pos-neg)))
    cat = 'Positive' if score > 0.6 else ('Negative' if score < 0.4 else 'Neutral')
    keywords = re.findall(r"\w{6,}", t)[:10]
    return cat, float(score), keywords, lang
