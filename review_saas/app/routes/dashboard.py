from fastapi import APIRouter, Depends
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import func, and_, between
    from datetime import datetime
    from ..db import engine
    from ..models import Review, Company
    from ..utils.security import get_current_user_id

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    @router.get("/kpis")
    def kpis(company_id: int | None = None, start: str | None = None, end: str | None = None, user_id: int = Depends(get_current_user_id)):
        with SessionLocal() as s:
            q = s.query(Review)
            if company_id:
                co = s.get(Company, company_id)
                if not co or co.owner_id != user_id:
                    return {"total_reviews":0,"avg_rating":0,"mix":{"positive":0,"neutral":0,"negative":0}}
                q = q.filter(Review.company_id==company_id)
            else:
                ids = [c.id for c in s.query(Company).filter(Company.owner_id==user_id).all()]
                if not ids:
                    return {"total_reviews":0,"avg_rating":0,"mix":{"positive":0,"neutral":0,"negative":0}}
                q = q.filter(Review.company_id.in_(ids))
            if start and end:
                try:
                    sdt = datetime.fromisoformat(start); edt = datetime.fromisoformat(end)
                    q = q.filter(Review.review_at.between(sdt, edt))
                except Exception:
                    pass
            total = q.count()
            avg = q.with_entities(func.avg(Review.rating)).scalar() or 0
            pos = q.filter(Review.sentiment=='positive').count()
            neu = q.filter(Review.sentiment=='neutral').count()
            neg = q.filter(Review.sentiment=='negative').count()
            return {"total_reviews": total, "avg_rating": round(avg,2), "mix": {"positive": pos, "neutral": neu, "negative": neg}}

    @router.get("/trend")
    def trend(company_id: int, user_id: int = Depends(get_current_user_id)):
        with SessionLocal() as s:
            co = s.get(Company, company_id)
            if not co or co.owner_id != user_id:
                return {"labels":[],"data":[]}
            rows = s.query(func.strftime('%Y-%m', Review.review_at), func.avg(Review.rating)).                filter(Review.company_id==company_id).group_by(func.strftime('%Y-%m', Review.review_at)).all()
            labels = [r[0] for r in rows]
            data = [round(r[1] or 0,2) for r in rows]
            return {"labels": labels, "data": data}

    @router.get("/recent")
    def recent(company_id: int, limit: int = 10, user_id: int = Depends(get_current_user_id)):
        with SessionLocal() as s:
            co = s.get(Company, company_id)
            if not co or co.owner_id != user_id:
                return []
            rows = s.query(Review).filter(Review.company_id==company_id).order_by(Review.review_at.desc()).limit(max(1,min(limit,100))).all()
            return [{"id": r.id, "text": r.text, "rating": r.rating, "sentiment": r.sentiment, "at": r.review_at.isoformat() if r.review_at else None} for r in rows]