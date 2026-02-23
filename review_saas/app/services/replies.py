# FILE: app/services/replies.py
from typing import List, Optional, Dict

"""
English-only reply suggester for hotel reviews.

Public API:
    suggest(
        review_text: str,
        sentiment: Optional[str] = None,           # 'positive' | 'negative' | 'neutral' | None (inferred)
        *,
        aspects: Optional[List[str]] = None,       # e.g., ["Service","Cleanliness","Price"]
        tone: str = "polite",                      # 'polite' | 'concise' | 'empathetic' | 'professional'
        hotel_name: str = "Our Hotel",
        contact: str = "support@example.com",      # email/phone/URL
        add_invite: bool = True,
        add_closing: bool = True,
        max_len: int = 600
    ) -> str

Notes:
- We never echo back the original review verbatim.
- We avoid including PII; do not insert reviewer names.
- Keep replies brief and respectful; clamped by max_len.
"""

MAX_LEN = 600  # A safe cap for common platforms; adjust per channel.

_NEGATIVE_TRIGGERS = {
    "bad", "terrible", "awful", "worst", "poor", "dirty", "noise", "noisy", "expensive", "rude"
}
_POSITIVE_TRIGGERS = {
    "great", "excellent", "love", "amazing", "best", "perfect", "wonderful", "clean", "friendly"
}


# Common hotel aspects we might receive from analysis
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
        "Quality": "room and amenities quality",
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
    Returns template snippets for English based on tone.
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


def suggest(
    review_text: str,
    sentiment: Optional[str] = None,
    *,
    aspects: Optional[List[str]] = None,
    tone: str = "polite",
    hotel_name: str = "Our Hotel",
    contact: str = "support@example.com",
    add_invite: bool = True,
    add_closing: bool = True,
    max_len: int = MAX_LEN
) -> str:
    """
    Generate a suggested owner reply for a hotel review (English only).
    """
    s = _infer_sentiment(review_text, sentiment)
    t = _english_templates(tone)
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
