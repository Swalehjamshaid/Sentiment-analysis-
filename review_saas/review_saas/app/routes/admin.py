
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Company, Review

router = APIRouter(prefix='/admin', tags=['admin'])

@router.get('/stats')
async def stats(db: Session = Depends(get_db)):
    return {
        'users': db.query(User).count(),
        'companies': db.query(Company).count(),
        'reviews': db.query(Review).count(),
        'avg_rating': db.query(Review).with_entities((Review.rating)).all()
    }
