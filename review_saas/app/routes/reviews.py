from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Company, Review
from app.schemas import ReviewCreate
from app.utils.ai import generate_ai_answer
from datetime import datetime, timedelta
from fastapi import Depends

router = APIRouter(prefix="/api", tags=["Reviews"])

# ---------------------------
# 1. Fetch Company List
# ---------------------------
@router.get("/companies")
def get_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).all()
    return [{"id": c.id, "name": c.name} for c in companies]

# ---------------------------
# 2. Add New Company
# ---------------------------
@router.post("/companies")
def add_company(company: ReviewCreate, db: Session = Depends(get_db)):
    new_company = Company(
        name=company.name,
        place_id=company.place_id,
        address=company.address,
        created_at=datetime.utcnow()
    )
    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    return {"id": new_company.id, "name": new_company.name}

# ---------------------------
# 3. Ingest Reviews (Scraper Trigger)
# ---------------------------
@router.post("/reviews/ingest/{company_id}")
def ingest_reviews(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Simulate scraper ingestion
    from app.utils.scraper import fetch_reviews_for_company
    reviews_list = fetch_reviews_for_company(company.place_id)

    # Save reviews to DB
    count = 0
    for r in reviews_list:
        review = Review(
            company_id=company.id,
            reviewer_name=r.get("reviewer_name"),
            rating=r.get("rating"),
            comment=r.get("comment"),
            sentiment=r.get("sentiment"),
            created_at=r.get("created_at", datetime.utcnow())
        )
        db.add(review)
        count += 1
    db.commit()
    return {"reviews_count": count}

# ---------------------------
# 4. AI Insights & KPIs
# ---------------------------
@router.get("/ai/insights")
def get_ai_insights(company_id: int, start: str = None, end: str = None, db: Session = Depends(get_db)):
    start_dt = datetime.strptime(start, "%Y-%m-%d") if start else datetime.utcnow() - timedelta(days=365)
    end_dt = datetime.strptime(end, "%Y-%m-%d") if end else datetime.utcnow()

    reviews = db.query(Review).filter(
        Review.company_id == company_id,
        Review.created_at >= start_dt,
        Review.created_at <= end_dt
    ).all()

    total_reviews = len(reviews)
    avg_rating = round(sum([r.rating for r in reviews]) / total_reviews, 2) if total_reviews > 0 else 0

    # Sentiment trend (weekly)
    trend = {}
    for r in reviews:
        week = r.created_at.strftime("%Y-%W")
        if week not in trend:
            trend[week] = []
        trend[week].append(r.sentiment or 0)
    sentiment_trend = [{"week": w, "avg": round(sum(v)/len(v), 2)} for w, v in trend.items()]

    # Emotion Radar (simulate)
    emotions = {"happy": 0, "angry": 0, "sad": 0, "neutral": 0}
    for r in reviews:
        s = r.sentiment or 0
        if s > 0.5:
            emotions["happy"] += 1
        elif s < -0.5:
            emotions["angry"] += 1
        elif -0.5 <= s < 0:
            emotions["sad"] += 1
        else:
            emotions["neutral"] += 1

    # Ratings distribution
    ratings_dist = {1:0,2:0,3:0,4:0,5:0}
    for r in reviews:
        ratings_dist[r.rating] += 1

    return {
        "metadata": {"total_reviews": total_reviews},
        "kpis": {
            "benchmark": {"your_avg": avg_rating},
            "reputation_score": round(sum([r.sentiment or 0 for r in reviews]),2)
        },
        "visualizations": {
            "emotions": emotions,
            "sentiment_trend": sentiment_trend,
            "ratings": ratings_dist
        }
    }

# ---------------------------
# 5. Revenue Risk Endpoint
# ---------------------------
@router.get("/dashboard/revenue")
def revenue_risk(company_id: int, db: Session = Depends(get_db)):
    # Simple example: risk based on number of negative reviews
    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    if not reviews:
        return {"risk_percent": 0, "impact": "N/A"}

    negative_count = len([r for r in reviews if (r.sentiment or 0) < -0.3])
    total = len(reviews)
    risk_percent = round((negative_count / total) * 100, 2)

    impact = "High" if risk_percent > 50 else "Medium" if risk_percent > 20 else "Low"

    return {"risk_percent": risk_percent, "impact": impact}

# ---------------------------
# 6. AI Chat Endpoint
# ---------------------------
@router.post("/dashboard/chat")
async def ai_chat(company_id: int, request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    question = payload if isinstance(payload, str) else payload.get("question", "")
    if not question:
        raise HTTPException(status_code=400, detail="No question provided")

    # Simulate AI response
    reviews = db.query(Review).filter(Review.company_id == company_id).all()
    answer = generate_ai_answer(question, reviews)  # from utils.ai

    return JSONResponse({"answer": answer})
