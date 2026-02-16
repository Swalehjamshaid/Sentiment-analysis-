
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from io import BytesIO
from ..db import get_db
from ..models import Company, Review, SuggestedReply
from ..services.pdf_report import generate_company_report

router = APIRouter(prefix='/reports', tags=['reports'])

@router.get('/company/{company_id}.pdf')
async def company_report(company_id: int, db: Session = Depends(get_db)):
    c = db.query(Company).get(company_id)
    if not c:
        raise HTTPException(status_code=404, detail='Not found')
    total = db.query(Review).filter(Review.company_id==company_id).count()
    avg = db.query(Review).filter(Review.company_id==company_id).with_entities(Review.rating).all()
    ratings = [r[0] for r in avg if r[0] is not None]
    avg_rating = round(sum(ratings)/len(ratings),2) if ratings else 0
    kpis = {
        'Total Reviews': total,
        'Average Rating': avg_rating
    }
    # No chart images in this MVP, pass empty dict
    samples = []
    for r in db.query(Review).filter(Review.company_id==company_id).limit(10).all():
        samples.append(f"[{r.rating}★] {r.reviewer_name}: { (r.text or '')[:200] }")
    buf = BytesIO()
    generate_company_report(buf, c, kpis, {}, samples)
    buf.seek(0)
    return StreamingResponse(buf, media_type='application/pdf', headers={'Content-Disposition': f"inline; filename=company_{company_id}.pdf"})
