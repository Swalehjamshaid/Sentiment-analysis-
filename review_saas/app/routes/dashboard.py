from fastapi import APIRouter, Depends
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import func
    from ..db import engine
    from ..models import Review, Company
    from ..utils.security import get_current_user_id

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    @router.get("/kpis")
    def kpis(user_id: int = Depends(get_current_user_id)):
        with SessionLocal() as s:
            company_ids = [c.id for c in s.query(Company).filter(Company.owner_id==user_id).all()]
            if not company_ids:
                return {"total_reviews": 0, "avg_rating": 0, "mix": {"positive": 0, "neutral": 0, "negative": 0}}
            total = s.query(func.count(Review.id)).filter(Review.company_id.in_(company_ids)).scalar() or 0
            avg = s.query(func.avg(Review.rating)).filter(Review.company_id.in_(company_ids)).scalar() or 0
            pos = s.query(func.count(Review.id)).filter(Review.company_id.in_(company_ids), Review.sentiment=="positive").scalar() or 0
            neu = s.query(func.count(Review.id)).filter(Review.company_id.in_(company_ids), Review.sentiment=="neutral").scalar() or 0
            neg = s.query(func.count(Review.id)).filter(Review.company_id.in_(company_ids), Review.sentiment=="negative").scalar() or 0
            return {"total_reviews": total, "avg_rating": round(avg,2), "mix": {"positive": pos, "neutral": neu, "negative": neg}}