
# filename: app/routes/exports.py
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io
import pandas as pd
from ..core.db import get_db
from ..models.models import Review

router = APIRouter(prefix='/exports', tags=['exports'])

@router.get('/csv')
def export_csv(company_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Review)
    if company_id:
        q = q.filter(Review.company_id==company_id)
    rows = [
        {'id': r.id, 'company_id': r.company_id, 'rating': r.rating, 'sentiment': r.sentiment_category, 'text': r.text} for r in q
    ]
    df = pd.DataFrame(rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type='text/csv', headers={'Content-Disposition':'attachment; filename=reviews.csv'})

@router.get('/xlsx')
def export_xlsx(company_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Review)
    if company_id:
        q = q.filter(Review.company_id==company_id)
    rows = [
        {'id': r.id, 'company_id': r.company_id, 'rating': r.rating, 'sentiment': r.sentiment_category, 'text': r.text} for r in q
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    buf.seek(0)
    return StreamingResponse(buf, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition':'attachment; filename=reviews.xlsx'})
