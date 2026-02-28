# filename: app/emailer.py
import smtplib
from email.message import EmailMessage
from .core.config import settings

def send_email(to_email: str, subject: str, html_body: str):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg['To'] = to_email
    msg.set_content('This is an HTML email. Open in an HTML capable client.')
    msg.add_alternative(html_body, subtype='html')

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
            s.starttls()
            if settings.SMTP_USERNAME:
                s.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            s.send_message(msg)
    except Exception as e:
        # In production, log to monitoring; here we fail-soft
        print(f"SMTP send failed: {e}")
