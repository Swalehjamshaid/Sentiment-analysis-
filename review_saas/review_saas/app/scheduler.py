
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from datetime import datetime
from .db import SessionLocal
from .models import Company, Review, Notification, FetchJob
from .services.google_places import fetch_reviews
from .services.sentiment import star_based_category, clean_text, sentiment_score, detect_keywords
from .services.replies import suggest_reply
from .services.emailer import send_email
import asyncio

scheduler = BackgroundScheduler()

async def run_fetch_job_async():
    db: Session = SessionLocal()
    try:
        jobs = db.query(FetchJob).all()
        from datetime import timedelta
        now = datetime.utcnow()
        for j in jobs:
            c = db.query(Company).get(j.company_id)
            if not c or c.status!='Active':
                continue
            if j.schedule=='weekly' and j.last_run and (now - j.last_run) < timedelta(days=7):
                continue
            if j.schedule=='daily' and j.last_run and (now - j.last_run) < timedelta(days=1):
                continue
            if not c.place_id:
                continue
            try:
                raw, _ = await fetch_reviews(c.place_id)
            except Exception:
                continue
            from .models import SuggestedReply
            for r in raw:
                from sqlalchemy.exc import IntegrityError
                text = (r.get('text') or '')[:5000]
                if not text and not r.get('rating'):
                    continue
                rev = Review(
                    company_id=c.id,
                    source='google',
                    external_id=str(r.get('external_id')),
                    text=text,
                    rating=r.get('rating'),
                    review_datetime=datetime.utcfromtimestamp(r.get('review_datetime')) if r.get('review_datetime') else None,
                    reviewer_name=r.get('reviewer_name') or 'Anonymous',
                    reviewer_pic_url=r.get('reviewer_pic_url'),
                )
                cat = star_based_category(rev.rating)
                ct = clean_text(text)
                s = sentiment_score(ct)
                kws = detect_keywords(ct)
                rev.sentiment_category = cat
                rev.sentiment_score = s
                rev.keywords = kws
                try:
                    db.add(rev); db.commit(); db.refresh(rev)
                    sr = SuggestedReply(review_id=rev.id, suggested_text=suggest_reply(ct, cat or 'Neutral'))
                    db.add(sr); db.commit()
                    if cat == 'Negative':
                        try:
                            send_email(c.owner.email if c.owner and c.owner.email else 'owner@example.com', 'New Negative Review', f"Company {c.name}: {ct[:200]}")
                            notif = Notification(user_id=c.owner_user_id, type='negative_review', payload=ct[:500])
                            db.add(notif); db.commit()
                        except Exception:
                            pass
                except IntegrityError:
                    db.rollback()
                except Exception:
                    db.rollback()
    
        # Rating drop alert (30-day vs previous 30-day)
        try:
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            for c in db.query(Company).all():
                cur = db.query(Review).filter(Review.company_id==c.id, Review.review_datetime != None, Review.review_datetime >= now - timedelta(days=30)).with_entities(Review.rating).all()
                prev = db.query(Review).filter(Review.company_id==c.id, Review.review_datetime != None, Review.review_datetime < now - timedelta(days=30), Review.review_datetime >= now - timedelta(days=60)).with_entities(Review.rating).all()
                if cur and prev:
                    avg_cur = sum([x[0] for x in cur if x[0]])/len(cur)
                    avg_prev = sum([x[0] for x in prev if x[0]])/len(prev)
                    if avg_prev - avg_cur >= 1.0:
                        try:
                            send_email(c.owner.email if c.owner and c.owner.email else 'owner@example.com', 'Alert: Rating Drop', f'Avg rating dropped from {avg_prev:.2f} to {avg_cur:.2f}')
                            notif = Notification(user_id=c.owner_user_id, type='rating_drop', payload=f'{avg_prev:.2f}->{avg_cur:.2f}')
                            db.add(notif); db.commit()
                        except Exception:
                            pass
        except Exception:
            pass
    
    finally:
        db.close()

def run_fetch_job():
    asyncio.run(run_fetch_job_async())


def start():
    scheduler.add_job(run_fetch_job, 'cron', hour=2, minute=0, id='daily_fetch', replace_existing=True)
    if not scheduler.running:
        scheduler.start()
