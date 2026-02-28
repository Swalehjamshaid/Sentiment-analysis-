# filename: app/services/emailer.py
from __future__ import annotations
import smtplib
import logging
from email.mime.text import MIMEText
from email.utils import formataddr
from jinja2 import Environment, select_autoescape, FileSystemLoader
from ..core.settings import settings

logger = logging.getLogger('app.emailer')
_env = Environment(loader=FileSystemLoader('app/templates'), autoescape=select_autoescape(['html', 'xml']))

def render_template(name: str, **ctx) -> str:
    tpl = _env.get_template(name)
    return tpl.render(**ctx)

def send_email(to_email: str, subject: str, html_body: str):
    if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        # Development Log
        logger.info(f"SMTP not configured. Email to: {to_email} | Subject: {subject}")
        return

    msg = MIMEText(html_body, 'html')
    msg['From'] = formataddr((settings.SMTP_FROM_NAME, settings.SMTP_FROM_EMAIL))
    msg['To'] = to_email
    msg['Subject'] = subject

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, [to_email], msg.as_string())
            logger.info(f"Email sent to {to_email}")
    except Exception as e:
        logger.error(f"SMTP error: {e}")
