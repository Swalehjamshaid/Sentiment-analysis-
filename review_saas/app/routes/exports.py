# filename: app/app/routes/exports.py
import io, csv
import pandas as pd
from pandas import DataFrame
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db import get_db
from app.models import Review, Company

router = APIRouter(tags=['export'])

@router.get('/api/export/activity.csv')
def export_csv(db: Session = Depends(get_db)):
    q = (
        db.query(Review.created_at, Review.source, Company.name, Review.sentiment, Review.text)
          .join(Company, Company.id == Review.company_id)
          .order_by(desc(Review.created_at))
          .limit(1000)
    )
    f = io.StringIO()
    w = csv.writer(f)
    w.writerow(['when','source','company','sentiment','text'])
    for r in q:
        w.writerow([r[0].isoformat() if r[0] else '', r[1], r[2], r[3], (r[4] or '').replace('
',' ')])
    f.seek(0)
    return StreamingResponse(iter([f.read()]), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="activity.csv"'})

@router.get('/api/export/activity.xlsx')
def export_xlsx(db: Session = Depends(get_db)):
    q = (
        db.query(Review.created_at, Review.source, Company.name, Review.sentiment, Review.text)
          .join(Company, Company.id == Review.company_id)
          .order_by(desc(Review.created_at))
          .limit(1000)
    )
    rows = [
        {'when': r[0].isoformat() if r[0] else '', 'source': r[1], 'company': r[2], 'sentiment': r[3], 'text': (r[4] or '').replace('
',' ') }
        for r in q
    ]
    df = DataFrame(rows)
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='activity', index=False)
    bio.seek(0)
    return StreamingResponse(bio, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename="activity.xlsx"'})
