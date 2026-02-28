
# filename: app/routes/reviews.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..models.models import Review

router = APIRouter(prefix='/reviews', tags=['reviews'])

@router.get('')
def list_reviews(company_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Review)
    if company_id:
        q = q.filter(Review.company_id==company_id)
    return [
        {
            'id': r.id,
            'company_id': r.company_id,
            'rating': r.rating,
            'sentiment': r.sentiment_category,
            'text': (r.text or '')[:200]
        } for r in q.order_by(Review.id.desc()).limit(200)
    ]
