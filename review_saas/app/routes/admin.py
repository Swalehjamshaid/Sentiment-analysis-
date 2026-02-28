
# filename: app/routes/admin.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..models.models import User, Company, Review

router = APIRouter(prefix='/admin', tags=['admin'])

@router.get('/stats')
def stats(db: Session = Depends(get_db)):
    return {
        'users': db.query(User).count(),
        'companies': db.query(Company).count(),
        'reviews': db.query(Review).count(),
    }
