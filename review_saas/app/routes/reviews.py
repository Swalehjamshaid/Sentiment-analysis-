import os
    from fastapi import APIRouter, HTTPException, Depends
    from sqlalchemy.orm import sessionmaker
    from datetime import datetime
    from ..db import engine
    from ..models import Review, Company
    from ..utils.security import get_current_user_id
    import httpx

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/reviews", tags=["reviews"])

    async def fetch_google_reviews(place_id: str, max_count: int = 100):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return [{"review_id": f"demo-{i}", "text": f"Sample review {i}", "rating": 5, "time": datetime.utcnow().isoformat(), "author_name": "Demo"} for i in range(min(max_count, 20))]
        # TODO: implement real Places call with pagination + retries
        return []

    def simple_sentiment(text: str):
        t = (text or "").lower()
        pos = sum(w in t for w in ["great","good","excellent","love","amazing","best"]) 
        neg = sum(w in t for w in ["bad","poor","terrible","hate","awful","worst"]) 
        score = max(0.0, min(1.0, 0.5 + 0.15*(pos-neg)))
        cat = "positive" if score>0.6 else ("negative" if score<0.4 else "neutral")
        return cat, int(score*100)

    @router.post("/fetch/{company_id}")
    async def fetch(company_id: int, count: int = 100, user_id: int = Depends(get_current_user_id)):
        with SessionLocal() as s:
            c = s.get(Company, company_id)
            if not c or c.owner_id != user_id:
                raise HTTPException(status_code=404, detail="Company not found")
        data = await fetch_google_reviews(c.place_id or "demo", max_count=min(max(count,1),500))
        created = 0
        with SessionLocal() as s:
            for item in data:
                ext_id = str(item.get("review_id") or item.get("id") or f"ts-{datetime.utcnow().timestamp()}-{created}")
                exists = s.query(Review).filter(Review.company_id==company_id, Review.external_id==ext_id).first()
                if exists: continue
                text = (item.get("text") or "")[:5000]
                cat, score = simple_sentiment(text)
                r = Review(company_id=company_id, external_id=ext_id, text=text, rating=int(item.get("rating") or 0), review_at=datetime.utcnow(), reviewer_name=item.get("author_name"), sentiment=cat, sentiment_score=score, fetch_status="Success")
                s.add(r); created += 1
            s.commit()
        return {"fetched": created}