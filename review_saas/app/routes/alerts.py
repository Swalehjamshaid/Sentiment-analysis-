# File 8: alerts.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Review, Company, User
from ..schemas import AlertCreate
import smtplib, os
from email.mime.text import MIMEText

router = APIRouter(prefix="/alerts", tags=["Alerts"])

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME")

def send_email(to_email: str, subject: str, content: str):
    msg = MIMEText(content)
    msg["Subject"] = subject
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)

@router.post("/negative-review")
def alert_negative_review(alert: AlertCreate, db: Session = Depends(get_db)):
    review = db.query(Review).filter_by(id=alert.review_id).first()
    if not review:
        return {"error": "Review not found"}
    company = db.query(Company).filter_by(id=review.company_id).first()
    user = db.query(User).filter_by(id=company.user_id).first()
    send_email(user.email, f"New Negative Review for {company.name}", f"Review: {review.text}")
    return {"detail": "Alert sent"}
