from fastapi import APIRouter
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import func
    from ..db import engine
    from ..models import Review

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    @router.get("/kpis")
    def kpis():
        with SessionLocal() as s:
            total = s.query(func.count(Review.id)).scalar() or 0
            avg = s.query(func.avg(Review.rating)).scalar() or 0
            pos = s.query(func.count(Review.id)).filter(Review.sentiment=="positive").scalar() or 0
            neu = s.query(func.count(Review.id)).filter(Review.sentiment=="neutral").scalar() or 0
            neg = s.query(func.count(Review.id)).filter(Review.sentiment=="negative").scalar() or 0
            return {"total_reviews": total, "avg_rating": round(avg,2), "mix": {"positive": pos, "neutral": neu, "negative": neg}}