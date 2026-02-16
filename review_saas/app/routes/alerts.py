
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from ..db import get_db
from ..models import Review

router = APIRouter(prefix='/alerts', tags=['alerts'])

@router.get('/keywords/{company_id}')
async def recurring_keywords(company_id: int, min_count: int = 3, days: int = 30, db: Session = Depends(get_db)):
    import json
    from collections import Counter
    since = datetime.utcnow() - timedelta(days=days)
    kws=[]
    for r in db.query(Review).filter(Review.company_id==company_id, Review.review_datetime==None or Review.review_datetime>=since).all():
        if r.keywords:
            kws.extend(json.loads(r.keywords))
    ctr = Counter(kws)
    return [{'keyword':k,'count':v} for k,v in ctr.items() if v>=min_count]
