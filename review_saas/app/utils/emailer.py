import os, smtplib
    from email.mime.text import MIMEText
    from ..core.config import settings

    def send_email(to: str, subject: str, body: str):
        host, user, pwd, port = settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASS, settings.SMTP_PORT
        sender = settings.FROM_EMAIL
        if not host or not user or not pwd:
            print(f"[EMAIL STUB] To:{to} | {subject}
{body}")
            return
        msg = MIMEText(body, 'plain')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = to
        with smtplib.SMTP(host, port) as s:
            s.starttls(); s.login(user, pwd); s.sendmail(sender, [to], msg.as_string())