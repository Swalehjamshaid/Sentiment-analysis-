
# filename: app/routes/exports.py
from __future__ import annotations
import io
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review

router = APIRouter(tags=['export'])

@router.get('/api/export/reviews.csv')
async def export_reviews_csv(company_id: int | None = None):
    async with get_session() as session:
        stmt = select(Review)
        if company_id: stmt = stmt.where(Review.company_id==company_id)
        rows = (await session.execute(stmt)).scalars().all()
    df = pd.DataFrame([{ 'company_id': r.company_id, 'rating': r.rating, 'text': r.text, 'sentiment': r.sentiment_compound, 'review_time': r.review_time } for r in rows])
    stream = io.StringIO(); df.to_csv(stream, index=False); stream.seek(0)
    return StreamingResponse(stream, media_type='text/csv', headers={'Content-Disposition':'attachment; filename=reviews.csv'})

@router.get('/api/export/reviews.xlsx')
async def export_reviews_xlsx(company_id: int | None = None):
    async with get_session() as session:
        stmt = select(Review)
        if company_id: stmt = stmt.where(Review.company_id==company_id)
        rows = (await session.execute(stmt)).scalars().all()
    df = pd.DataFrame([{ 'company_id': r.company_id, 'rating': r.rating, 'text': r.text, 'sentiment': r.sentiment_compound, 'review_time': r.review_time } for r in rows])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    buf.seek(0)
    return StreamingResponse(buf, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition':'attachment; filename=reviews.xlsx'})

@router.get('/api/export/summary.pdf')
async def export_summary_pdf(company_id: int | None = None):
    # Minimal PDF summary
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=A4)
    c.setFont('Helvetica', 12)
    c.drawString(50, 800, 'ReviewSaaS — Summary')
    c.drawString(50, 780, f'Company ID: {company_id or "All"}')
    c.drawString(50, 760, 'This is a minimal PDF summary placeholder.')
    c.showPage(); c.save()
    packet.seek(0)
    return StreamingResponse(packet, media_type='application/pdf', headers={'Content-Disposition':'attachment; filename=summary.pdf'})
