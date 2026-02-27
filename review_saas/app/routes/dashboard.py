# filename: app/app/routes/dashboard.py
from datetime import datetime, timedelta
from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db import get_db
from app.models import Review, Company

router = APIRouter(tags=['dashboard'])

@router.get('/api/kpis')
def kpis(db: Session = Depends(get_db)) -> Dict[str, Any]:
    total_reviews = db.query(func.count(Review.id)).scalar() or 0
    companies = db.query(func.count(Company.id)).scalar() or 0
    avg_sentiment = db.query(func.avg(Review.sentiment)).scalar() or 0
    since = datetime.utcnow() - timedelta(days=14)
    new_14d = db.query(func.count(Review.id)).filter(Review.created_at >= since).scalar() or 0
    return {
        'total_reviews': int(total_reviews),
        'avg_sentiment': round(float(avg_sentiment or 0), 3),
        'new_14d': int(new_14d),
        'companies': int(companies),
    }

@router.get('/api/category-mix')
def category_mix(db: Session = Depends(get_db)) -> Dict[str, Any]:
    labels: List[str] = []
    values: List[int] = []
    from collections import Counter
    c = Counter()
    for name, types in db.query(Company.name, Company.types).all():
        if not types:
            continue
        try:
            import json
            arr = json.loads(types) if types.strip().startswith('[') else [t.strip() for t in types.split(',') if t.strip()]
        except Exception:
            arr = [t.strip() for t in types.split(',') if t.strip()]
        c.update(arr)
    for k, v in c.most_common():
        labels.append(k)
        values.append(v)
    return {'labels': labels, 'values': values}

@router.get('/api/orders/series')
def orders_series(days: int = 14, db: Session = Depends(get_db)) -> Dict[str, Any]:
    end = datetime.utcnow().date()
    start = end - timedelta(days=days - 1)
    q = (
        db.query(func.date(Review.created_at).label('d'), func.count(Review.id))
          .filter(func.date(Review.created_at).between(start, end))
          .group_by('d')
          .order_by('d')
    )
    counts = {str(d): int(c) for d, c in q.all()}
    labels, values = [], []
    cur = start
    while cur <= end:
        s = str(cur)
        labels.append(s)
        values.append(counts.get(s, 0))
        cur += timedelta(days=1)
    return {'labels': labels, 'values': values}

@router.get('/api/activity')
def activity(limit: int = 100, db: Session = Depends(get_db)) -> Dict[str, Any]:
    rows = (
        db.query(Review.created_at, Review.source, Company.name, Review.sentiment, Review.text)
          .join(Company, Company.id == Review.company_id)
          .order_by(Review.created_at.desc())
          .limit(limit)
          .all()
    )
    items = [
        {
            'when': r[0].isoformat() if r[0] else None,
            'source': r[1],
            'company': r[2],
            'sentiment': r[3],
            'text': (r[4] or '')[:240],
        }
        for r in rows
    ]
    return {'items': items}
