# FILE: review_saas/app/services/replies.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import re

router = APIRouter(prefix="/api/replies", tags=["replies"])

# ─────────────────────────────────────────────────────────────
# Lightweight NLP helpers (aligned with your reviews logic)
# ─────────────────────────────────────────────────────────────
_STOPWORDS = {
    "a","an","and","are","as","at","be","by","for","from","the","this","is","it","to",
    "with","was","of","in","on","or","we","you","our","your","but","not","they","them",
    "very","really","just","too","i","me","my","myself"
}

ASPECT_LEXICON: Dict[str, List[str]] = {
    "Service": ["service", "staff", "attitude", "rude", "friendly", "helpful", "manager", "waiter", "waitress"],
    "Speed": ["wait", "slow", "delay", "queue", "time", "late", "long"],
    "Price": ["price", "expensive", "cheap", "overpriced", "value", "cost", "rip"],
    "Cleanliness": ["clean", "dirty", "smell", "hygiene", "filthy", "bathroom"],
    "Quality": ["quality", "defect", "broken", "taste", "fresh", "stale", "cold", "hot"],
    "Availability": ["stock", "availability", "sold", "item", "out", "none"],
    "Environment": ["noise", "crowd", "parking", "space", "ambience", "loud", "temperature"],
    "Digital": ["payment", "card", "terminal", "app", "crash", "online", "wifi", "website"],
}

def _normalize(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[^\w\s]", " ", text.lower())

def extract_keywords(text: Optional[str]) -> List[str]:
    if not text:
        return []
    return [w for w in _normalize(text).split() if w not in _STOPWORDS and len(w) >= 3]

def map_aspects(tokens: List[str]) -> List[str]:
    found = set()
    for aspect, words in ASPECT_LEXICON.items():
        if any(w in tokens for w in words):
            found.add(aspect)
    return sorted(found)

def classify_sentiment_by_rating(rating: Optional[float]) -> str:
    if rating is None or rating == 3:
        return "Neutral"
    return "Positive" if rating >= 4 else "Negative"

# ─────────────────────────────────────────────────────────────
# Tone + Language banks
# ─────────────────────────────────────────────────────────────
TONE_PRESETS = {
    "polite": {
        "style": "polite",
        "opening_en": "Thank you for sharing your feedback.",
        "opening_ur": "آپ کی رائے دینے کا شکریہ۔",
    },
    "concise": {
        "style": "concise",
        "opening_en": "Thanks for your review.",
        "opening_ur": "آپ کے ریویو کا شکریہ۔",
    },
    "apologetic": {
        "style": "apologetic",
        "opening_en": "We’re sorry for the experience you had.",
        "opening_ur": "آپ کے تجربے پر ہمیں افسوس ہے۔",
    },
    "appreciative": {
        "style": "appreciative",
        "opening_en": "We truly appreciate your positive feedback!",
        "opening_ur": "ہم آپ کے مثبت فیڈبیک کے بہت شکر گزار ہیں!",
    },
}

SUPPORTED_LANGS = {"en", "ur"}

def _opening_line(tone: str, lang: str) -> str:
    t = TONE_PRESETS.get(tone, TONE_PRESETS["polite"])
    key = f"opening_{lang}"
    return t.get(key, t["opening_en"])

def _thank_you_line(sentiment: str, lang: str) -> str:
    if lang == "ur":
        return "ہمارے ساتھ اپنے خیالات بانٹنے کے لیے شکریہ۔" if sentiment != "Positive" else "خوشی ہے کہ آپ کا تجربہ اچھا رہا۔"
    return "Thank you for taking the time to share your thoughts." if sentiment != "Positive" else "We’re glad you had a good experience."

def _acknowledge_aspects(aspects: List[str], lang: str) -> str:
    if not aspects:
        return ""
    if lang == "ur":
        return f"ہم نے درج ذیل نکات نوٹ کیے ہیں: {', '.join(aspects)}۔"
    return f"We’ve noted the following areas: {', '.join(aspects)}."

def _next_steps(aspects: List[str], sentiment: str, lang: str) -> str:
    if sentiment == "Negative" and aspects:
        if lang == "ur":
            return "ہم ان نکات پر فوری نظر ثانی کریں گے اور بہتری کے اقدامات نافذ کریں گے۔"
        return "We will review these points promptly and implement corrective actions."
    if sentiment == "Neutral" and aspects:
        if lang == "ur":
            return "مزید بہتری کے لیے ہم ان نکات کو اپنی ٹیم کے ساتھ شیئر کریں گے۔"
        return "We’ll share these notes with the team to improve further."
    if sentiment == "Positive":
        if lang == "ur":
            return "آپ کے مثبت الفاظ ہماری ٹیم کا حوصلہ بڑھاتے ہیں۔"
        return "Your positive words encourage our team."
    return ""

def _invite_back(lang: str) -> str:
    return "We hope to welcome you again soon." if lang == "en" else "ہم امید کرتے ہیں کہ جلد آپ کی دوبارہ میزبانی کریں گے۔"

def _signoff(company_name: Optional[str], lang: str) -> str:
    if lang == "ur":
        return f"— ٹیم {company_name}" if company_name else "— ٹیم"
    return f"— Team {company_name}" if company_name else "— Team"

# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────
def generate_reply(
    review_text: str,
    rating: Optional[float],
    company_name: Optional[str] = None,
    tone: str = "polite",
    language: str = "en",
    max_chars: int = 800
) -> Dict[str, Any]:
    """
    Creates an owner reply draft. No external APIs used.
    - Uses rating to set sentiment (±/0).
    - Extracts aspects via keyword mapping.
    - Obeys tone (polite/concise/apologetic/appreciative) and language (en/ur).
    """
    lang = language if language in SUPPORTED_LANGS else "en"
    sentiment = classify_sentiment_by_rating(rating)
    toks = extract_keywords(review_text)
    aspects = map_aspects(toks)

    # Choose default tone by sentiment if caller passed unknown tone
    if tone not in TONE_PRESETS:
        tone = "apologetic" if sentiment == "Negative" else ("appreciative" if sentiment == "Positive" else "polite")

    parts = [
        _opening_line(tone, lang),
        _thank_you_line(sentiment, lang),
        _acknowledge_aspects(aspects, lang),
        _next_steps(aspects, sentiment, lang),
        _invite_back(lang),
        _signoff(company_name, lang)
    ]

    # Join and trim
    reply = " ".join(p for p in parts if p).strip()
    if max_chars and len(reply) > max_chars:
        reply = reply[:max_chars - 1].rstrip() + "…"

    return {
        "reply": reply,
        "meta": {
            "sentiment": sentiment,
            "tone": tone,
            "language": lang,
            "aspects": aspects
        }
    }

def batch_generate_replies(
    items: List[Dict[str, Any]],
    company_name: Optional[str] = None,
    tone: str = "polite",
    language: str = "en",
    max_chars: int = 800
) -> List[Dict[str, Any]]:
    """
    items: [{ 'text': str, 'rating': int|float, 'id': optional }]
    Returns list with same order; each has {id?, reply, meta}.
    """
    out: List[Dict[str, Any]] = []
    for it in items:
        r = generate_reply(
            review_text=it.get("text", "") or "",
