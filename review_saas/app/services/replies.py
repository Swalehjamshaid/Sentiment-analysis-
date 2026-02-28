# filename: app/services/replies.py

def generate_reply(rating: int, text: str) -> str:
    base_pos = "Thank you for your kind words! We appreciate your support."
    base_neu = "Thank you for the feedback. We'll keep improving."
    base_neg = (
        "We're sorry for the experience. Please contact us at support@example.com so we can help."
    )
    if rating is None:
        return base_neu
    if rating >= 4:
        return base_pos
    if rating == 3:
        return base_neu
    return base_neg
