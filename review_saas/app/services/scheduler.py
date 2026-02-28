
# filename: app/services/scheduler.py
from __future__ import annotations
from apscheduler.schedulers.background import BackgroundScheduler
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy.orm import Session
from ..core.db import SessionLocal
from ..models.models import Company, Review
from .google_reviews import fetch_reviews
from .sentiment import classify

scheduler = BackgroundScheduler()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _sync_company_reviews(db: Session, company: Company):
    if not company.place_id:
        return
    incoming = fetch_reviews(company.place_id, page_size=100)
    for r in incoming:
        exists = db.query(Review).filter(Review.company_id==company.id, Review.external_id==r.get('external_id')).first()
        if exists:
            continue
        cat, score = classify(r.get('text'), r.get('rating'))
        obj = Review(
            company_id=company.id,
            external_id=r.get('external_id'),
            text=r.get('text')[:5000] if r.get('text') else None,
            rating=r.get('rating'),
            reviewer_name=r.get('reviewer_name'),
            reviewer_avatar=r.get('reviewer_avatar'),
            sentiment_category=cat,
            sentiment_score=score,
            fetch_status='Success'
        )
        db.add(obj)
    db.commit()


def daily_job():
    db = SessionLocal()
    try:
        companies = db.query(Company).all()
        for c in companies:
            _sync_company_reviews(db, c)
    finally:
        db.close()


def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(daily_job, 'interval', days=1, id='daily_reviews')
    scheduler.start()
