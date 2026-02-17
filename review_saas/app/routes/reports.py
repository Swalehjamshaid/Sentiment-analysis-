from fastapi import APIRouter
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import func
    from pathlib import Path
    from datetime import datetime
    import pandas as pd

    from ..db import engine
    from ..models import Company, Review

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/reports", tags=["reports"])

    @router.post("/pdf/{company_id}")
    def pdf(company_id: int):
        Path("outputs").mkdir(parents=True, exist_ok=True)
        with SessionLocal() as s:
            company = s.get(Company, company_id)
            if not company:
                return {"error": "Company not found"}
            total = s.query(func.count(Review.id)).filter(Review.company_id==company_id).scalar() or 0
            avg = s.query(func.avg(Review.rating)).filter(Review.company_id==company_id).scalar() or 0
            path = f"outputs/report_{company.name.replace(' ','_')}.pdf"
            c = canvas.Canvas(path, pagesize=A4)
            w, h = A4
            c.setFont("Helvetica-Bold", 16)
            c.drawString(40, h-60, f"Reputation Report — {company.name}")
            c.setFont("Helvetica", 10)
            c.drawString(40, h-80, f"Generated: {datetime.utcnow().isoformat()}Z")
            y = h-120
            c.drawString(40, y, f"Total reviews: {total}"); y -= 14
            c.drawString(40, y, f"Average rating: {round(avg,2)}"); y -= 24
            # sample
            reviews = s.query(Review).filter(Review.company_id==company_id).order_by(Review.review_at.desc()).limit(10).all()
            c.setFont("Helvetica-Bold", 12); c.drawString(40, y, "Sample Reviews:"); y -= 18
            c.setFont("Helvetica", 10)
            for rv in reviews:
                txt = (rv.text or "").strip()[:200]
                c.drawString(40, y, f"- {rv.rating}★ {rv.sentiment}: {txt}")
                y -= 14
                if y < 80:
                    c.showPage(); y = h-80
            c.showPage(); c.save()
            return {"path": path}

    @router.get("/export/{company_id}")
    def export(company_id: int, fmt: str = "csv"):
        Path("outputs").mkdir(parents=True, exist_ok=True)
        with SessionLocal() as s:
            rows = s.query(Review).filter(Review.company_id==company_id).all()
            data = [{"id": r.id, "text": r.text, "rating": r.rating, "sentiment": r.sentiment, "score": r.sentiment_score, "review_at": r.review_at.isoformat() if r.review_at else None} for r in rows]
            df = pd.DataFrame(data)
            if fmt == "excel":
                out = f"outputs/company_{company_id}_reviews.xlsx"
                df.to_excel(out, index=False)
            else:
                out = f"outputs/company_{company_id}_reviews.csv"
                df.to_csv(out, index=False)
            return {"path": out}