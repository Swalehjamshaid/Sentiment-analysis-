
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from ..config import SMTP


def send_email(to_email: str, subject: str, html_body: str):
    msg = MIMEText(html_body, 'html')
    msg['Subject'] = subject
    msg['From'] = formataddr(('Reputation SaaS', SMTP['from']))
    msg['To'] = to_email

    with smtplib.SMTP(SMTP['host'], SMTP['port']) as server:
        server.starttls()
        if SMTP['user']:
            server.login(SMTP['user'], SMTP['password'])
        server.sendmail(SMTP['from'], [to_email], msg.as_string())
