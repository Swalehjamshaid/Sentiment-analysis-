# dashboard.py
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List, Dict
from app.database import get_db
from app.models import Company, Review
from app.schemas import ReviewSchema, CompanySchema
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# -----------------------------
# FRONTEND ROUTE
# -----------------------------
@router.get("/")
async def dashboard_page(request: Request):
    """
    Renders the dashboard.html page
    """
    return templates.TemplateResponse("dashboard.html", {"request": request})

# -----------------------------
# API ROUTES
# -----------------------------
@router.get("/api/companies")
async def get_companies(db: Session = get_db()):
    companies = db.query(Company).all()
    result = [{"id": c.id, "name": c.name, "place_id": c.place_id, "address": c.address} for c in companies]
    return JSONResponse(content={"companies": result})

@router.post("/api/companies")
async def add_company(payload: CompanySchema, db: Session = get_db()):
    company = Company(name=payload.name, place_id=payload.place_id, address=payload.address)
    db.add(company)
    db.commit()
    db.refresh(company)
    return JSONResponse(content={"status": "success", "id": company.id})

# -----------------------------
# KPI + CHART DATA
# -----------------------------
@router.get("/api/dashboard/ai/insights")
async def get_ai_insights(company_id: int, start: Optional[str] = None, end: Optional[str] = None, db: Session = get_db()):
    start_dt = datetime.fromisoformat(start) if start else datetime(2024, 1, 1)
    end_dt = datetime.fromisoformat(end) if end else datetime.now()

    reviews = db.query(Review).filter(
        Review.company_id == company_id,
        Review.date >= start_dt,
        Review.date <= end_dt
    ).all()

    if not reviews:
        return JSONResponse(content={"metadata": {}, "kpis": {}, "visualizations": {}})

    # KPI calculations
    total_reviews = len(reviews)
    avg_rating = round(sum(r.rating for r in reviews) / total_reviews, 2)
    reputation_score = round(sum(r.reputation_score for r in reviews) / total_reviews, 2)

    # Charts
    emotions = {}
    sentiment_trend = {}
    ratings_dist = {1:0,2:0,3:0,4:0,5:0}

    for r in reviews:
        for emo, val in r.emotions.items():
            emotions[emo] = emotions.get(emo, 0) + val
        week_key = r.date.strftime("%Y-%W")
        if week_key not in sentiment_trend:
            sentiment_trend[week_key] = {"avg": r.sentiment, "count": 1}
        else:
            sentiment_trend[week_key]["avg"] += r.sentiment
            sentiment_trend[week_key]["count"] += 1
        ratings_dist[r.rating] += 1

    # Average sentiment per week
    sentiment_trend_list = [{"week": k, "avg": round(v["avg"]/v["count"], 2)} for k,v in sorted(sentiment_trend.items())]

    vis = {
        "emotions": {k: round(v,2) for k,v in emotions.items()},
        "sentiment_trend": sentiment_trend_list,
        "ratings": ratings_dist
    }

    kpis = {
        "average_rating": avg_rating,
        "reputation_score": reputation_score
    }

    metadata = {
        "total_reviews": total_reviews
    }

    return JSONResponse(content={"metadata": metadata, "kpis": kpis, "visualizations": vis})

# -----------------------------
# Revenue Risk
# -----------------------------
@router.get("/api/dashboard/revenue")
async def revenue_risk(company_id: int, db: Session = get_db()):
    # Dummy calculation; replace with real business logic
    risk_percent = 10  # %
    impact_level = "Medium"  # e.g., Low, Medium, High
    return JSONResponse(content={"risk_percent": risk_percent, "impact": impact_level})

# -----------------------------
# Review Sync
# -----------------------------
@router.post("/api/reviews/ingest/{company_id}")
async def ingest_reviews(company_id: int, db: Session = get_db()):
    """
    Syncs live reviews from Google Places API or SERP API (placeholder)
    """
    # Placeholder logic: Fetch reviews from API
    # Here you would call your scraper or external API to get reviews
    new_reviews_count = 5  # Dummy number

    # Optionally save dummy reviews
    # for i in range(new_reviews_count):
    #     review = Review(company_id=company_id, rating=5, sentiment=0.9, emotions={"happy":1}, date=datetime.now(), reputation_score=0.8)
    #     db.add(review)
    # db.commit()

    return JSONResponse(content={"status": "success", "reviews_count": new_reviews_count})

# -----------------------------
# AI Chatbot
# -----------------------------
@router.post("/chatbot/chat")
async def chat_ai(request: Request, db: Session = get_db()):
    data = await request.json()
    message = data.get("message")
    company_id = data.get("company_id")
    if not message or not company_id:
        raise HTTPException(status_code=400, detail="Missing parameters")

    # Dummy AI response (replace with real AI integration)
    answer = f"Simulated AI response to '{message}' for company ID {company_id}"
    return JSONResponse(content={"answer": answer})
