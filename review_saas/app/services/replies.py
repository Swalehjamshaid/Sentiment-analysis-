# FILE: review_saas/app/services/replies.py
"""
Reply assistant for hotel reviews.

Features
- generate_reply(): drafts a single owner reply from rating + text
- batch_generate_replies(): drafts replies for a list of reviews
- Tone presets: polite, apologetic, brief, professional
- Simple keyword/aspect extraction (no external libs)
- Action suggestions mapped from detected issues

NOTE:
- Safe to use server-side for pre-drafting; you can still edit before posting.
- If you already have aspect mining in reviews.py, you can pass aspects=... to
  generate_reply() to skip re-parsing.
"""

from typing import Dict, List, Optional, Tuple
import re
from collections import Counter

# ─────────────────────────────────────────────────────────────
# NLP helpers (lightweight; mirrors your reviews.py choices)
# ─────────────────────────────────────────────────────────────
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "the", "this", "is", "it", "to", "with", "was", "of", "in", "on",
    "or", "we", "you", "our", "your", "but", "not", "they", "them",
    "very", "really", "just", "too", "i", "me", "my", "myself"
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

ACTION_MAP: Dict[str, str] = {
    "wait": "we are adjusting peak-hour staffing and queue management.",
    "service": "we are reinforcing our service standards with additional training.",
    "rude": "we’ve reminded our team about our code of conduct and are coaching on soft skills.",
    "price": "we’re reviewing pricing versus local competitors to ensure fair value.",
    "clean": "we’ve added extra cleaning checks and supervision.",
    "quality": "we’re auditing suppliers and tightening our quality checks.",
    "stock": "we’re improving demand forecasting and restocking alerts.",
    "noise": "we’re evaluating acoustic improvements and quieter seating.",
    "payment": "we’re monitoring devices and working with our provider to prevent terminal issues.",
}

def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", (text or "").lower())

def _keywords(text: str) -> List[str]:
    words = _normalize(text).split()
    return [w for w in words if w not in _STOPWORDS and len(w) >= 3]

def _map_aspects_from_text(text: str) -> Tuple[List[str], List[str]]:
    toks = _keywords(text)
    aspects: List[str] = []
    for aspect, vocab in ASPECT_LEXICON.items():
        if any(w in toks for w in vocab):
            aspects.append(aspect)
    common = [w for w, _ in Counter(toks).most_common(5)]
    return aspects, common

def _action_from_tokens(tokens: List[str]) -> Optional[str]:
    for t in tokens:
        for k, action in ACTION_MAP.items():
            if k in t:
                return action
    return None

# ─────────────────────────────────────────────────────────────
# Tone presets & templates
# ─────────────────────────────────────────────────────────────
TONE_PREFIX = {
    "polite":       "Thank you for sharing this.",
    "apologetic":   "We’re truly sorry for the inconvenience.",
    "brief":        "Thanks for the feedback.",
    "professional": "Thank you for your feedback.",
}

TONE_SIGNOFF = {
    "polite":       "We hope to welcome you again.",
    "apologetic":   "We appreciate the chance to make this right.",
    "brief":        "We’ll improve.",
    "professional": "Regards,\nManagement Team",
}

POSITIVE_PHRASE = "We’re thrilled you had a good experience."
NEUTRAL_PHRASE  = "We appreciate your balanced feedback."
NEGATIVE_PHRASE = "We take your concerns seriously and are acting on them."

def _cap(s: str, max_chars: int) -> str:
    if max_chars and len(s) > max_chars:
        return s[: max_chars - 1].rstrip() + "…"
    return s

# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────
def generate_reply(
    text: str,
    rating: Optional[int] = None,
    *,
    company_name: Optional[str] = None,
    reviewer_name: Optional[str] = None,
    tone: str = "polite",
    language: str = "en",
    aspects: Optional[List[str]] = None,
    max_chars: int = 1200
) -> Dict[str, str]:
    tone = tone if tone in TONE_PREFIX else "polite"
    prefix = TONE_PREFIX[tone]
    signoff = TONE_SIGNOFF[tone]

    if rating is None or rating == 3:
        band = "neutral"
        mid = NEUTRAL_PHRASE
    elif rating >= 4:
        band = "positive"
        mid = POSITIVE_PHRASE
    else:
        band = "negative"
        mid = NEGATIVE_PHRASE

    if aspects is None:
        aspects, tokens = _map_aspects_from_text(text)
    else:
        _, tokens = _map_aspects_from_text(text)

    action_hint = None
    if band == "negative":
        action_hint = _action_from_tokens(tokens)
    if not action_hint and aspects:
        action_hint = {
            "Service": "we’re reinforcing our service standards.",
            "Speed": "we’re improving queue and service speed.",
            "Price": "we’ll review our pricing and value offers.",
            "Cleanliness": "we’re increasing cleaning audits.",
            "Quality": "we’re strengthening quality checks.",
            "Availability": "we’re improving stock availability.",
            "Environment": "we’re improving ambience and comfort.",
            "Digital": "we’re ensuring smoother digital payments and Wi‑Fi.",
        }.get(aspects[0], None)

    subj_company = f" for {company_name}" if company_name else ""
    subject = f"Thanks for your review{subj_company}"

    addressed = f"Hi {reviewer_name}," if reviewer_name else "Hello,"
    aspect_line = ""
    if aspects:
        aspect_line = " We’ve noted your points about " + ", ".join(aspects[:3]) + "."

    action_line = f" For transparency, {action_hint}" if action_hint else ""

    body = (
        f"{addressed}\n\n"
        f"{prefix} {mid}{aspect_line}{action_line}\n\n"
        f"If you’d like to discuss further, please contact the duty manager at the front desk or via this profile."
        f"\n\n{signoff}"
    )

    return {
        "subject": _cap(subject, 120),
        "reply": _cap(body, max_chars),
        "aspects": aspects or [],
        "action_hint": action_hint or "",
        "tone": tone,
        "sentiment_band": band,
        "language": language,
    }

def batch_generate_replies(
    reviews: List[Dict[str, Optional[str]]],
    *,
    company_name: Optional[str] = None,
    tone: str = "polite",
    max_chars: int = 1200
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for r in reviews:
        reply = generate_reply(
            r.get("text") or "",
            rating=r.get("rating"),
            company_name=company_name,
            reviewer_name=r.get("reviewer_name"),
            tone=tone,
            max_chars=max_chars
        )
        reply["review_id"] = r.get("id")
        out.append(reply)
    return out

# ─────────────────────────────────────────────────────────────
# Fix for "ImportError: cannot import name 'suggest'"
# ─────────────────────────────────────────────────────────────
# Provide a 'suggest' alias for backwards compatibility
suggest = generate_reply
