# app/services/replies.py
from typing import List, Optional, Dict

# If you later want to fetch company defaults (email/phone) from DB, you can
# import get_db and query within a helper. Kept simple and stateless for now.
# from ..db import get_db

MAX_LEN = 600  # A safe cap for Google/OTA platforms; adjust per channel.

_NEGATIVE_TRIGGERS = {"bad", "terrible", "awful", "worst", "poor", "dirty", "noise", "noisy", "expensive", "rude"}
_POSITIVE_TRIGGERS = {"great", "excellent", "love", "amazing", "best", "perfect", "wonderful", "clean", "friendly"}

# Common hotel aspects we might receive from analysis:
# e.g., ["Service","Cleanliness","Price","Environment","Quality","Speed","Digital","Availability"]
def _select_aspect_line(aspects: List[str]) -> str:
    if not aspects:
        return ""
    # map to human-friendly words
    readable = {
        "Service": "our service",
        "Cleanliness": "cleanliness",
        "Price": "pricing and value",
        "Environment": "noise or comfort",
        "Quality": "room/amenities quality",
        "Speed": "check-in speed and responsiveness",
        "Digital": "Wi‑Fi and digital services",
        "Availability": "availability and stock",
    }
    picked = [readable.get(a, a.lower()) for a in aspects][:3]
    # Return a short clause that acknowledges up to 3 aspects
    if len(picked) == 1:
        return f" We’re reviewing {picked[0]} with the team."
    if len(picked) == 2:
        return f" We’re reviewing {picked[0]} and {picked[1]} with the team."
    return f" We’re reviewing {picked[0]}, {picked[1]}, and {picked[2]} with the team."


def _clamp(text: str, limit: int = MAX_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _infer_sentiment(review_text: str, sentiment_hint: Optional[str]) -> str:
    s = (sentiment_hint or "").strip().lower()
    if s in {"positive", "negative", "neutral"}:
        return s
    t = (review_text or "").lower()
    if any(w in t for w in _NEGATIVE_TRIGGERS):
        return "negative"
    if any(w in t for w in _POSITIVE_TRIGGERS):
        return "positive"
    return "neutral"


def _english_templates(tone: str) -> Dict[str, str]:
    """
    Returns small template snippets for English based on tone.
    tone ∈ {polite, concise, empathetic, professional}
    """
    base = {
        "greet": "Thank you for taking the time to share feedback.",
        "brand": "{hotel_name}",
        "contact": "Please reach us at {contact} so we can assist you directly.",
        "commit": "We appreciate your feedback and will keep improving.",
        "invite": "We hope to welcome you again.",
        "apology": "We’re sorry to hear about your experience.",
        "thanks": "We’re grateful for your kind words.",
        "closing": "Warm regards,\n{hotel_name} Team",
    }
    if tone == "concise":
        base.update({
            "greet": "Thanks for the feedback.",
            "apology": "Sorry for the trouble.",
            "thanks": "Thanks for the kind words.",
            "commit": "We’ll use this to improve.",
            "closing": "Regards,\n{hotel_name}",
        })
    elif tone == "empathetic":
        base.update({
            "apology": "We’re truly sorry this fell short. Your comfort matters to us.",
            "commit": "We’re investigating and will take corrective action.",
            "closing": "Sincerely,\n{hotel_name} Management",
        })
    elif tone == "professional":
        base.update({
            "greet": "Thank you for your detailed feedback.",
            "commit": "Your comments have been escalated to the relevant department.",
            "closing": "Kind regards,\n{hotel_name}",
        })
    return base


def _urdu_templates(tone: str) -> Dict[str, str]:
    # Simple Urdu scaffolding; expand as needed.
    base = {
        "greet": "آپ کی رائے کا شکریہ۔",
        "brand": "{hotel_name}",
        "contact": "براہِ کرم {contact} پر رابطہ کریں تاکہ ہم براہِ راست مدد کر سکیں۔",
        "commit": "ہم آپ کی رائے کو بہتر کرنے کے لیے استعمال کریں گے۔",
        "invite": "ہم امید کرتے ہیں کہ آپ دوبارہ تشریف لائیں گے۔",
        "apology": "آپ کے ناخوشگوار تجربے پر ہمیں افسوس ہے۔",
        "thanks": "اچھے الفاظ کے لیے شکریہ۔",
        "closing": "نیک تمنائیں،\n{hotel_name} ٹیم",
    }
    if tone == "concise":
        base.update({
            "greet": "رائے کا شکریہ۔",
            "apology": "معذرت خواہ ہیں۔",
            "closing": "شکریہ،\n{hotel_name}",
        })
    return base


def _pick_lang_templates(language: str, tone: str) -> Dict[str, str]:
    lang = (language or "en").lower()
    if lang.startswith("ur"):
        return _urdu_templates(tone)
    # default English
    return _english_templates(tone)


def suggest(
    review_text: str,
    sentiment: Optional[str] = None,
    *,
    aspects: Optional[List[str]] = None,
    tone: str = "polite",
    hotel_name: str = "Our Hotel",
    contact: str = "support@example.com",
    language: str = "en",
    add_invite: bool = True,
    add_closing: bool = True,
    max_len: int = MAX_LEN
) -> str:
    """
    Generate a suggested owner reply for a hotel review.

    Args:
        review_text: Original review text (never echoed back verbatim).
        sentiment: Optional 'positive' | 'negative' | 'neutral'. If omitted, inferred heuristically.
        aspects: Optional list of aspect names, e.g., ["Service","Cleanliness","Price"].
        tone: One of 'polite' | 'concise' | 'empathetic' | 'professional'.
        hotel_name: Brand shown in the signature.
        contact: Email/phone/URL for direct resolution.
        language: 'en' (default) or 'ur' scaffolded; extend as needed.
        add_invite: Include a welcoming line.
        add_closing: Include closing signature.
        max_len: Character clamp to keep the response platform-safe.

    Returns:
        str: A crafted reply, clamped to max_len.
    """
    s = _infer_sentiment(review_text, sentiment)
    t = _pick_lang_templates(language, tone)
    parts: List[str] = []

    # Greeting or thanks
    if s == "positive":
        parts.append(t["thanks"])
    else:
        parts.append(t["greet"])

    # Sentiment-specific core
    if s == "negative":
        parts.append(t["apology"])
        # Aspect-aware line
        aspects_line = _select_aspect_line(aspects or [])
        if aspects_line:
            parts.append(aspects_line.strip())
        # Offer direct help
        parts.append(t["contact"].format(contact=contact))
        parts.append(t["commit"])
    elif s == "neutral":
        # Neutral acknowledgment
        aspects_line = _select_aspect_line(aspects or [])
        if aspects_line:
            parts.append(aspects_line.strip())
        parts.append(t["commit"])
    else:  # positive
        parts.append(t["commit"])

    if add_invite and s != "negative":
        parts.append(t["invite"])

    if add_closing:
        parts.append(t["closing"].format(hotel_name=hotel_name))

    # Never echo PII; do not include reviewer name; keep short & respectful.
    reply = " ".join(p for p in parts if p).strip()
    return _clamp(reply, limit=max_len)
