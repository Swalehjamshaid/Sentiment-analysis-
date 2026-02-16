
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from ..db import get_db
from ..models import Review, Company

router = APIRouter(prefix='/dashboard', tags=['dashboard'])

@router.get('/summary/{company_id}')
async def summary(company_id: int, db: Session = Depends(get_db)):
    c = db.query(Company).get(company_id)
    if not c:
        raise HTTPException(status_code=404, detail='Not found')
    total = db.query(func.count(Review.id)).filter(Review.company_id == company_id).scalar() or 0
    avg_rating = db.query(func.avg(Review.rating)).filter(Review.company_id == company_id).scalar()
    pos = db.query(func.count(Review.id)).filter(Review.company_id == company_id, Review.sentiment_category=='Positive').scalar() or 0
    neu = db.query(func.count(Review.id)).filter(Review.company_id == company_id, Review.sentiment_category=='Neutral').scalar() or 0
    neg = db.query(func.count(Review.id)).filter(Review.company_id == company_id, Review.sentiment_category=='Negative').scalar() or 0
    return {
        'total_reviews': total,
        'avg_rating': round(avg_rating or 0, 2),
        'positive_pct': round((pos/total*100) if total else 0, 2),
        'neutral_pct': round((neu/total*100) if total else 0, 2),
        'negative_pct': round((neg/total*100) if total else 0, 2),
    }

@router.get('/trend/{company_id}')
async def trend(company_id: int, db: Session = Depends(get_db)):
    q = db.query(
        func.strftime('%Y-%m', Review.review_datetime).label('period'),
        func.avg(Review.rating),
        func.count(Review.id)
    ).filter(Review.company_id == company_id, Review.review_datetime.isnot(None)).group_by('period').order_by('period')
    return [{'period': p, 'avg_rating': float(a or 0), 'count': int(c)} for p, a, c in q]

@router.get('/keywords/{company_id}')
async def keywords(company_id: int, db: Session = Depends(get_db)):
    # naive keyword counts
    import json
    from collections import Counter
    kws = []
    for r in db.query(Review).filter(Review.company_id==company_id).all():
        if r.keywords:
            kws.extend(json.loads(r.keywords))
    ctr = Counter(kws)
    return [{'keyword': k, 'count': v} for k, v in ctr.most_common(50)]

from fastapi.responses import FileResponse
import pandas as pd
import tempfile, os

@router.get('/export/{company_id}')
async def export(company_id: int, fmt: str = 'csv', db: Session = Depends(get_db)):
    rows = db.query(Review).filter(Review.company_id==company_id).all()
    data = [{
        'id': r.id,
        'rating': r.rating,
        'text': r.text,
        'date': r.review_datetime,
        'sentiment': r.sentiment_category,
        'score': r.sentiment_score
    } for r in rows]
    df = pd.DataFrame(data)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{fmt}')
    tmp.close()
    if fmt=='xlsx':
        df.to_excel(tmp.name, index=False, engine='openpyxl')
        media='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        df.to_csv(tmp.name, index=False)
        media='text/csv'
    return FileResponse(tmp.name, media_type=media, filename=f'company_{company_id}_export.{fmt}')
