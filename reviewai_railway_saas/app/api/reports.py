from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import AsyncSessionLocal
from .. import models
from .deps import get_current_user
from ..services.pdf import generate_company_report

router = APIRouter(prefix="/reports", tags=["reports"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/company/{company_id}/pdf")
async def company_pdf(company_id: int, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    q = await db.execute(select(models.Company).where(models.Company.id == company_id, models.Company.user_id == user.id))
    company = q.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    q2 = await db.execute(select(models.Review).where(models.Review.company_id == company.id))
    reviews = q2.scalars().all()

    total = len(reviews)
    avg = sum([r.star_rating or 0 for r in reviews])/total if total else 0
    pos = sum(1 for r in reviews if r.sentiment == 'Positive')
    neu = sum(1 for r in reviews if r.sentiment == 'Neutral')
    neg = sum(1 for r in reviews if r.sentiment == 'Negative')

    # Simplified trend (by month)
    from collections import defaultdict
    trend = defaultdict(list)
    for r in reviews:
        if r.review_date:
            key = r.review_date.strftime('%Y-%m')
            trend[key].append(r.star_rating or 0)
    ratings_trend = sorted([(k, sum(v)/len(v)) for k, v in trend.items()])

    samples = {
        'Positive': [{ 'text': r.review_text or '', 'reply': (r.reply.suggested_reply if r.reply else '') } for r in reviews if r.sentiment=='Positive'][:3],
        'Negative': [{ 'text': r.review_text or '', 'reply': (r.reply.suggested_reply if r.reply else '') } for r in reviews if r.sentiment=='Negative'][:3],
    }

    pdf = generate_company_report(company.name,
                                  {
                                      'total_reviews': total,
                                      'average_rating': avg,
                                      'pct_positive': (pos/total*100 if total else 0),
                                      'pct_neutral': (neu/total*100 if total else 0),
                                      'pct_negative': (neg/total*100 if total else 0)
                                  },
                                  ratings_trend,
                                  {'Positive': pos, 'Neutral': neu, 'Negative': neg},
                                  samples)
    return Response(content=pdf, media_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="review_report_{company.id}.pdf"'
    })