# app/services/replies.py

def suggest(review_text: str, sentiment: str | None = None) -> str:
    """
    Suggests a reply for a customer review based on its text and optional sentiment.
    
    Parameters:
    - review_text (str): The text of the customer review.
    - sentiment (str | None): Optional sentiment label, expected values "positive" or "negative".
    
    Returns:
    - str: A suggested reply message (up to 500 characters).
    
    Logic:
    1. Convert both review text and sentiment to lowercase for case-insensitive matching.
    2. Define comprehensive lists of positive and negative keywords.
    3. If sentiment is explicitly 'negative' OR any negative keywords are present in the text,
       return a polite apology with contact support.
    4. If sentiment is explicitly 'positive' OR any positive keywords are present in the text,
       return a thank you message appreciating the customer.
    5. For all other cases, return a neutral acknowledgment encouraging future feedback.
    6. The output is always truncated to 500 characters to avoid excessively long replies.
    """

    # Normalize input
    t = (review_text or "").strip().lower()
    s = (sentiment or "").strip().lower()

    # Extensive negative and positive keyword lists
    negative_words = [
        "bad", "terrible", "awful", "worst", "poor", "disappointed", "hate",
        "not satisfied", "frustrated", "angry", "problem", "issue", "broken",
        "slow", "ugly", "waste", "unhappy", "negative"
    ]
    positive_words = [
        "great", "excellent", "love", "amazing", "best", "awesome", "fantastic",
        "perfect", "happy", "satisfied", "good", "wonderful", "recommend", "pleased",
        "delighted", "positive"
    ]

    # Detect negative sentiment
    if s == "negative" or any(word in t for word in negative_words):
        return (
            "We’re sorry about your experience. "
            "Please contact support@example.com so we can help."
        )[:500]

    # Detect positive sentiment
    if s == "positive" or any(word in t for word in positive_words):
        return (
            "Thank you for your kind words! "
            "We truly appreciate your feedback."
        )[:500]

    # Default neutral response for unclear sentiment
    return (
        "Thanks for sharing your thoughts. "
        "We value your feedback and will keep improving."
    )[:500]
