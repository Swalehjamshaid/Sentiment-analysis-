# review_saas/app/services/replies.py

def suggest(review_text: str, sentiment: str | None = None) -> str:
    t = (review_text or "").lower()
    s = (sentiment or "").lower()

    if s == 'negative' or any(w in t for w in ['bad','terrible','awful','worst','poor']):
        return "We’re sorry about your experience. Please contact support@example.com so we can help."[:500]

    if s == 'positive' or any(w in t for w in ['great','excellent','love','amazing','best']):
        return "Thank you for your kind words! We truly appreciate your feedback."[:500]

    return "Thanks for sharing your thoughts. We value your feedback and will keep improving."[:500]
