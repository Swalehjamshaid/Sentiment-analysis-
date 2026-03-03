# filename: app/core/mailer.py
from __future__ import annotations
import smtplib
import logging
from email.mime.text import MIMEText
from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, html: str) -> dict:
    host = settings.SMTP_HOST
    username = settings.SMTP_USERNAME
    password = settings.SMTP_PASSWORD
    port = settings.SMTP_PORT
    from_email = settings.SMTP_FROM_EMAIL or username

    # If SMTP not configured → Dev fallback
    if not (host and username and password and from_email):
        print(
            "\n=== EMAIL (DEV MODE) ===\n"
            f"To: {to_email}\n"
            f"Subject: {subject}\n"
            f"{html}\n"
            "========================\n"
        )
        return {"sent": False, "dev": True}

    msg = MIMEText(html, "html")
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{from_email}>"
    msg["To"] = to_email

    try:
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls()
            s.login(username, password)
            s.sendmail(from_email, [to_email], msg.as_string())

        return {"sent": True}

    except OSError as e:
        # Network blocked (your current issue)
        logger.warning("SMTP network error: %s", str(e))

        print(
            "\n=== EMAIL FALLBACK (NETWORK BLOCKED) ===\n"
            f"To: {to_email}\n"
            f"Subject: {subject}\n"
            f"{html}\n"
            "========================================\n"
        )

        return {"sent": False, "network_blocked": True}

    except Exception as e:
        logger.error("Unexpected email error: %s", str(e))
        return {"sent": False, "error": str(e)}
