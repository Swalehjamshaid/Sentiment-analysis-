# app/services/replies.py

from ..db import get_db  # Correct import for database session

def suggest(review_text: str, sentiment: str | None = None) -> str:
    """
    Generate a suggested reply message for a review based on its text and sentiment.

    Args:
        review_text (str): The text of the customer's review.
        sentiment (str | None): Optional sentiment classification ('positive', 'negative', etc.).

    Returns:
        str: A reply message, truncated to 500 characters.
    """
    t = (review_text or "").lower()
    s = (sentiment or "").lower()

    # Negative sentiment triggers
    if s == "negative" or any(w in t for w in ["bad", "terrible", "awful", "worst", "poor"]):
        return "We’re sorry about your experience. Please contact support@example.com so we can help."[:500]

    # Positive sentiment triggers
    if s == "positive" or any(w in t for w in ["great", "excellent", "love", "amazing", "best"]):
        return "Thank you for your kind words! We truly appreciate your feedback."[:500]

    # Neutral / unspecified sentiment
    return "Thanks for sharing your thoughts. We value your feedback and will keep improving."[:500]
