
# filename: app/routes/dashboard.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..models.models import Company, Review

router = APIRouter(prefix='/dashboard', tags=['dashboard'])

@router.get('/kpis')
def kpis(company_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Review)
    if company_id:
        q = q.filter(Review.company_id==company_id)
    total = q.count()
    if total:
        avg = sum([r.rating or 0 for r in q]) / total
    else:
        avg = 0.0
    pos = q.filter(Review.sentiment_category=='Positive').count()
    neu = q.filter(Review.sentiment_category=='Neutral').count()
    neg = q.filter(Review.sentiment_category=='Negative').count()
    return {'total_reviews': total, 'avg_rating': round(avg,2), 'positive': pos, 'neutral': neu, 'negative': neg}
