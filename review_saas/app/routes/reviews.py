from fastapi import APIRouter, HTTPException, Depends
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from datetime import datetime
    from ..db import engine
    from ..models import Review, Company, User
    from ..utils.security import get_current_user_id
    from ..services.places import fetch_reviews
    from ..services.sentiment import analyze_text, stars_to_category
    from ..services.notifications import alert_negative_review

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/reviews", tags=["reviews"])

    @router.post("/fetch/{company_id}")
    async def fetch(company_id: int, count: int = 100, user_id: int = Depends(get_current_user_id)):
        with SessionLocal() as s:
            c = s.get(Company, company_id)
            if not c or c.owner_id != user_id:
                raise HTTPException(404, "Company not found")
            owner = s.get(User, user_id)
        data = await fetch_reviews(c.place_id or "demo", page_size=min(max(count,1),500))
        created = 0
        negatives = 0
        with SessionLocal() as s:
            for item in data:
                ext_id = str(item.get("review_id") or item.get("id") or f"ts-{datetime.utcnow().timestamp()}-{created}")
                if s.query(Review).filter(Review.company_id==company_id, Review.external_id==ext_id).first():
                    continue
                text = (item.get("text") or "")[:5000]
                # Combine star rule + text nuance
                star_cat = stars_to_category(int(item.get("rating") or 0))
                cat, score, kws, lang = analyze_text(text)
                final_cat = star_cat if star_cat != 'neutral' else cat
                r = Review(company_id=company_id, external_id=ext_id, text=text, rating=int(item.get("rating") or 0), review_at=datetime.utcnow(), reviewer_name=item.get("author_name"), sentiment=final_cat, sentiment_score=int(score*100), keywords=",".join(kws), language=lang, fetch_status="Success")
                s.add(r); created += 1
                if final_cat == 'negative':
                    negatives += 1
            s.commit()
            if negatives > 0:
                alert_negative_review(owner.email, c.name, f"{negatives} negative review(s) fetched")
        return {"fetched": created, "negatives": negatives}