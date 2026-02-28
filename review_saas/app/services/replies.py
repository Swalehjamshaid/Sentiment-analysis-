
# filename: app/services/replies.py
from __future__ import annotations

def suggest_reply(sentiment: str, reviewer_name: str | None = None) -> str:
    name = reviewer_name or 'there'
    if sentiment == 'Negative':
        return f"Hi {name}, we're sorry about your experience. Please contact us so we can make this right."
    if sentiment == 'Positive':
        return f"Hi {name}, thank you for your wonderful feedback! We appreciate your support."
    return f"Hi {name}, thanks for your review. We value your input."
