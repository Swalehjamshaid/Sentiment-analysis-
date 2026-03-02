
# filename: app/core/mailer.py
from __future__ import annotations
import smtplib
from email.mime.text import MIMEText
from app.core.config import settings

def send_email(to_email: str, subject: str, html: str) -> dict:
    host = settings.SMTP_HOST
    username = settings.SMTP_USERNAME
    password = settings.SMTP_PASSWORD
    port = settings.SMTP_PORT
    from_email = settings.SMTP_FROM_EMAIL or username
    if not (host and username and password and from_email):
        # Dev fallback: print to console
        print("
=== EMAIL (DEV) ===
To:", to_email, "
Subject:", subject, "
", html, "
===================
")
        return {"sent": False, "dev": True}
    msg = MIMEText(html, 'html')
    msg['Subject'] = subject
    msg['From'] = f"{settings.SMTP_FROM_NAME} <{from_email}>"
    msg['To'] = to_email
    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(username, password)
        s.sendmail(from_email, [to_email], msg.as_string())
    return {"sent": True}
