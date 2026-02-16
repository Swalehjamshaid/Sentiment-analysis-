
from datetime import datetime

def suggest_reply(text: str | None, category: str):
    base_contact = "If you'd like to discuss further, please contact us at support@example.com."
    if category == 'Negative':
        return "We're sorry about your experience. " + base_contact
    if category == 'Positive':
        return "Thank you for your kind words! We appreciate your support."
    return "Thank you for your feedback."
