
def suggest(review_text: str, sentiment: str | None = None) -> str:
    t = (review_text or "").strip().lower()
    s = (sentiment or "").strip().lower()
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
    if s == "negative" or any(word in t for word in negative_words):
        return ("We’re sorry about your experience. Please contact support@example.com so we can help.")[:500]
    if s == "positive" or any(word in t for word in positive_words):
        return ("Thank you for your kind words! We truly appreciate your feedback.")[:500]
    return ("Thanks for sharing your thoughts. We value your feedback and will keep improving.")[:500]
