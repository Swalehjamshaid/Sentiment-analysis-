from fastapi import APIRouter, HTTPException
    from sqlalchemy.orm import sessionmaker
    from datetime import datetime
    from ..db import engine
    from ..models import Review, Company

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/reviews", tags=["reviews"])

    def simple_sentiment(text: str) -> tuple[str, float, list[str]]:
        text = (text or "").lower()
        pos = sum(1 for w in ("great","good","excellent","love","amazing","best") if w in text)
        neg = sum(1 for w in ("bad","poor","terrible","hate","awful","worst") if w in text)
        score = max(0.0, min(1.0, 0.5 + 0.15*(pos-neg)))
        cat = "positive" if score>0.6 else ("negative" if score<0.4 else "neutral")
        keywords = [w for w in text.split() if len(w)>=6][:10]
        return cat, score, keywords

    @router.post("/fetch/{company_id}")
    def fetch(company_id: int, count: int = 50):
        # Stub: pretend we fetched count reviews successfully
        with SessionLocal() as s:
            company = s.get(Company, company_id)
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
            created = 0
            for i in range(max(1, min(count, 100))):
                text = f"Sample review {i} for {company.name} — great service"
                cat, score, kws = simple_sentiment(text)
                r = Review(company_id=company_id, text=text[:5000], rating=5, review_at=datetime.utcnow(), sentiment=cat, sentiment_score=int(score*100), keywords=",".join(kws))
                s.add(r); created += 1
            s.commit()
            return {"fetched": created}