from ..database import settings

def generate_reply(sentiment: str, reviewer_name: str | None = None, company_contact_email: str | None = None, company_contact_phone: str | None = None) -> str:
    contact_email = company_contact_email or settings.COMPANY_CONTACT_EMAIL
    contact_phone = company_contact_phone or settings.COMPANY_CONTACT_PHONE
    name = reviewer_name or "there"
    if sentiment == "Negative":
        return (
            f"Hi {name}, we're truly sorry about your experience. We'd love to make it right. "
            f"Please email us at {contact_email} or call {contact_phone} so our team can help promptly."
        )
    elif sentiment == "Neutral":
        return (
            f"Hi {name}, thank you for your feedback. We're always improving and would value any details "
            f"you can share at {contact_email}."
        )
    else:
        return (
            f"Hi {name}, thank you for the wonderful review! We appreciate your support and hope to see you again soon."
        )