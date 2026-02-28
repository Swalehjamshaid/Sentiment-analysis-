# filename: app/services/scheduler.py
from __future__ import annotations
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from ..core.db import SessionLocal
from ..models.models import Company, Review
from .google_reviews import fetch_reviews # Successfully imported now

logger = logging.getLogger('app.scheduler')
scheduler = BackgroundScheduler()

def daily_review_sync():
    """Requirement #54: Daily background sync for all active companies."""
    db: Session = SessionLocal()
    try:
        companies = db.query(Company).filter(Company.status == 'active').all()
        for company in companies:
            logger.info(f"Syncing reviews for: {company.name}")
            raw_reviews = fetch_reviews(company.place_id)
            
            for r in raw_reviews:
                # Requirement #70: Duplicate Check
                external_id = str(r.get('time'))
                exists = db.query(Review).filter(
                    Review.company_id == company.id, 
                    Review.external_id == external_id
                ).first()
                
                if not exists:
                    new_review = Review(
                        company_id=company.id,
                        external_id=external_id,
                        text=r.get('text'),
                        rating=r.get('rating'),
                        reviewer_name=r.get('author_name')
                    )
                    db.add(new_review)
            db.commit()
    except Exception as e:
        logger.error(f"Scheduler sync error: {e}")
    finally:
        db.close()

def start_scheduler():
    """Initializes the scheduler on app startup (Requirement #124)."""
    if not scheduler.running:
        scheduler.add_job(daily_review_sync, 'interval', days=1, id='daily_job')
        scheduler.start()
        logger.info("Background scheduler started.")
