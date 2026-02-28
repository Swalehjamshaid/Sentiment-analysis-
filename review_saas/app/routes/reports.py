# File 6: reports.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Company, Review, Reply
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io, os
from fastapi.responses import StreamingResponse
from datetime import datetime

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/company/{company_id}/pdf")
def generate_pdf(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    reviews = db.query(Review).filter_by(company_id=company_id).all()
    replies = db.query(Reply).join(Review).filter(Review.company_id==company_id).all()
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, f"Report for {company.name}")
    y -= 30
    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    y -= 30

    # Reviews summary
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Reviews:")
    y -= 20
    for r in reviews[:20]:  # limit for page
        text = r.text[:300] + ("..." if len(r.text) > 300 else "")
        c.setFont("Helvetica", 10)
        c.drawString(50, y, f"- {text} ({r.sentiment_category})")
        y -= 15
        if y < 100:
            c.showPage()
            y = height - 50

    # Suggested replies
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Suggested Replies:")
    y -= 20
    for rep in replies[:20]:
        c.setFont("Helvetica", 10)
        text = rep.user_edited_text if rep.user_edited_text else rep.suggested_text
        text = text[:300] + ("..." if len(text) > 300 else "")
        c.drawString(50, y, f"- {text}")
        y -= 15
        if y < 100:
            c.showPage()
            y = height - 50

    c.showPage()
    c.save()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={company.name}_report.pdf"})
