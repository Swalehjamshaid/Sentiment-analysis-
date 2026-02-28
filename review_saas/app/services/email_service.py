# filename: app/services/email_service.py
from ..core.config import Settings
import logging

log = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.settings = Settings()

    def send(self, to_email: str, subject: str, body: str):
        # Stub: in production, wire SMTP or provider here
        log.info("Sending email to %s :: %s", to_email, subject)
        # TODO: integrate SMTP using self.settings
        return True
