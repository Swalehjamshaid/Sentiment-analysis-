# filename: app/routes/exports.py
from __future__ import annotations
import csv
import io
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import get_current_user
from ..models.models import User, Company, Review

router = APIRouter(prefix='/exports', tags=['Data Export'])

@router.get("/csv/{company_id}")
async def export_reviews_csv(
    company_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """Requirement #105: Export all reviews for a company to CSV."""
    
    # Requirement #42: Security check - Verify ownership
    company = db.query(Company).filter(
        Company.id == company_id, 
        Company.owner_id == current_user.id
    ).first()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found or access denied")

    reviews = db.query(Review).filter(Review.company_id == company_id).all()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    writer.writerow(['Date', 'Reviewer', 'Rating', 'Sentiment', 'Score', 'Text'])
    
    for r in reviews:
        writer.writerow([
            r.review_date.strftime('%Y-%m-%d') if r.review_date else 'N/A',
            r.reviewer_name,
            r.rating,
            r.sentiment_category,
            r.sentiment_score,
            r.text
        ])

    output.seek(0)
    
    filename = f"reviews_{company.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/pdf-preview/{company_id}")
async def pdf_report_meta(
    company_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """Requirement #109: Prepare metadata for PDF Report generation."""
    company = db.query(Company).filter(
        Company.id == company_id, 
        Company.owner_id == current_user.id
    ).first()
    
    if not company:
        raise HTTPException(status_code=404, detail="Access denied")

    # This returns the data structure needed by your PDF generator service
    return {
        "company_name": company.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_reviews": db.query(Review).filter(Review.company_id == company_id).count()
    }
