
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from ..db import get_db
from ..models import Company, Review, SuggestedReply, Notification
from ..services.google_places import fetch_reviews
from ..services.sentiment import star_based_category, clean_text, sentiment_score, detect_keywords
from ..services.replies import suggest_reply
from ..services.emailer import send_email

router = APIRouter(prefix='/reviews', tags=['reviews'])

async def _save_reviews(db: Session, company: Company, raw_reviews: list):
    saved = 0; skipped = 0
    for r in raw_reviews:
        text = (r.get('text') or '')[:5000]
        if not text and not r.get('rating'):
            continue
        try:
            rev = Review(
                company_id=company.id,
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
            db.add(rev)
            db.commit(); db.refresh(rev)
            # Suggested reply
            sr = SuggestedReply(review_id=rev.id, suggested_text=suggest_reply(ct, cat or 'Neutral'))
            db.add(sr); db.commit()
            # Notify negative
            if cat == 'Negative':
                try:
                    to_email = company.owner.email if company.owner else None
                    if to_email:
                        send_email(to_email, 'New Negative Review', f"<p>{ct[:200]}</p>")
                    notif = Notification(user_id=company.owner_user_id, type='negative_review', payload=ct[:500])
                    db.add(notif); db.commit()
                except Exception:
                    pass
            saved += 1
        except Exception:
            db.rollback(); skipped += 1
    return saved, skipped

@router.post('/fetch/{company_id}')
async def manual_fetch(company_id: int, db: Session = Depends(get_db)):
    c = db.query(Company).get(company_id)
    if not c:
        raise HTTPException(status_code=404, detail='Company not found')
    if not c.place_id:
        raise HTTPException(status_code=400, detail='No Place ID on company')
    try:
        raw, _ = await fetch_reviews(c.place_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'Fetch failed: {e}')
    saved, skipped = await _save_reviews(db, c, raw)
    return {'saved': saved, 'skipped': skipped}

@router.get('/company/{company_id}')
async def list_reviews(company_id: int, db: Session = Depends(get_db)):
    revs = db.query(Review).filter(Review.company_id == company_id).order_by(Review.review_datetime.desc().nulls_last()).all()
    return [
        {
            'id': r.id,
            'company_id': r.company_id,
            'text': r.text,
            'rating': r.rating,
            'review_datetime': r.review_datetime.isoformat() if r.review_datetime else None,
            'reviewer_name': r.reviewer_name,
            'sentiment_category': r.sentiment_category,
            'sentiment_score': r.sentiment_score,
            'keywords': r.keywords
        } for r in revs
    ]
