from fastapi import APIRouter
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import func
    from pathlib import Path
    from ..db import engine
    from ..models import Company, Review
    from ..services.reports import build_pdf
    from ..services.export import export_reviews

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/reports", tags=["reports"])

    @router.post("/pdf/{company_id}")
    def pdf(company_id: int):
        Path("outputs").mkdir(parents=True, exist_ok=True)
        with SessionLocal() as s:
            co = s.get(Company, company_id)
            if not co: return {"error":"Company not found"}
            total = s.query(func.count(Review.id)).filter(Review.company_id==company_id).scalar() or 0
            avg = s.query(func.avg(Review.rating)).filter(Review.company_id==company_id).scalar() or 0
            kpis = {"Total reviews": total, "Average rating": round(avg,2)}
            samples = s.query(Review).filter(Review.company_id==company_id).order_by(Review.review_at.desc()).limit(10).all()
            samples = [{"text": r.text, "rating": r.rating, "sentiment": r.sentiment} for r in samples]
            path = f"outputs/report_{co.name.replace(' ','_')}.pdf"
            pdfp = build_pdf(path, co.name, kpis, samples)
            return {"path": pdfp}

    @router.get("/export/{company_id}")
    def export(company_id: int, fmt: str = 'csv'):
        Path("outputs").mkdir(parents=True, exist_ok=True)
        with SessionLocal() as s:
            rows = s.query(Review).filter(Review.company_id==company_id).all()
            data = [{"id": r.id, "text": r.text, "rating": r.rating, "sentiment": r.sentiment, "score": r.sentiment_score, "review_at": r.review_at.isoformat() if r.review_at else None} for r in rows]
            out = export_reviews(f"outputs/company_{company_id}_reviews", data, 'excel' if fmt=='excel' else 'csv')
            return {"path": out}