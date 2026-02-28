from ..core.settings import settings

    async def send_email(to: str, subject: str, body: str):
        # Stub - integrate real SMTP provider here.
        return {"sent": True, "to": to, "subject": subject}