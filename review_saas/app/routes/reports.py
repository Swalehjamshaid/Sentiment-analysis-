
# filename: app/routes/reports.py
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import io
from ..core.db import get_db
from ..models.models import Company, Review

router = APIRouter(prefix='/reports', tags=['reports'])

@router.get('/company.pdf')
def company_report(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise ValueError('Company not found')
    reviews = db.query(Review).filter(Review.company_id==company_id).limit(100).all()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont('Helvetica-Bold', 16)
    c.drawString(40, 800, f'Review Report: {company.name}')
    c.setFont('Helvetica', 10)
    y = 770
    for r in reviews:
        line = f"#{r.id} ★{r.rating or '-'} [{r.sentiment_category or '-'}] { (r.text or '')[:80]}"
        c.drawString(40, y, line)
        y -= 14
        if y < 60:
            c.showPage(); y = 800
    c.showPage(); c.save(); buf.seek(0)
    return StreamingResponse(buf, media_type='application/pdf', headers={'Content-Disposition':'attachment; filename=company_report.pdf'})
