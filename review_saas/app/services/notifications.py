from ..core.config import settings
    from ..utils.emailer import send_email

    def alert_negative_review(user_email: str, company_name: str, review_text: str):
        if not settings.ENABLE_ALERTS:
            return
        subject = f"Alert: New negative review for {company_name}"
        body = f"A negative review was detected for {company_name}:

{review_text[:500]}"
        send_email(user_email, subject, body)