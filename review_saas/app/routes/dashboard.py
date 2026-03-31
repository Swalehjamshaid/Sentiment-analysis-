# app/routes/dashboard.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import random
from datetime import datetime, timedelta
import os

# ==================== CREATE ROUTER ====================
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ===============================
# In-Memory Mock Database
# ===============================
companies_db = [
    {"id": "1", "name": "TechMart", "place_id": "abc123", "address": "123 Tech St"},
    {"id": "2", "name": "Cafe Deluxe", "place_id": "def456", "address": "456 Coffee Rd"},
]

reviews_db = {
    "1": [{"rating": random.randint(1, 5), "sentiment": random.uniform(0, 1), "emotion": random.choice(["Happy", "Angry", "Neutral"])} for _ in range(120)],
    "2": [{"rating": random.randint(1, 5), "sentiment": random.uniform(0, 1), "emotion": random.choice(["Happy", "Angry", "Neutral"])} for _ in range(80)],
}

# ===============================
# Pydantic Models
# ===============================
class CompanyCreate(BaseModel):
    name: str
    place_id: str
    address: str

class ChatMessage(BaseModel):
    message: str
    company_id: str

# ===============================
# HTML Dashboard (Serves your frontend)
# ===============================
@router.get("/", response_class=HTMLResponse)
async def get_dashboard():
    TEMPLATE_PATH = os.path.join("templates", "dashboard.html")
    if not os.path.exists(TEMPLATE_PATH):
        return HTMLResponse("<h1>Dashboard UI not found</h1><p>Please upload templates/dashboard.html</p>")
    
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

# ===============================
# API Endpoints (Exactly matching your frontend JS)
# ===============================
@router.get("/api/companies")
async def get_companies():
    return {"companies": companies_db}

@router.post("/api/companies")
async def add_company(company: CompanyCreate):
    new_id = str(len(companies_db) + 1)
    companies_db.append({
        "id": new_id,
        "name": company.name,
        "place_id": company.place_id,
        "address": company.address,
    })
    reviews_db[new_id] = []
    return {"status": "success", "company_id": new_id}

@router.get("/api/ai/insights")
async def get_ai_insights(company_id: str, start: Optional[str] = None, end: Optional[str] = None):
    if company_id not in reviews_db:
        raise HTTPException(status_code=404, detail="Company not found")

    reviews = reviews_db[company_id]
    total_reviews = len(reviews)
    avg_rating = round(sum(r["rating"] for r in reviews) / total_reviews, 2) if total_reviews else 0

    emotions_count = {"Happy": 0, "Angry": 0, "Neutral": 0}
    ratings_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    for r in reviews:
        emotions_count[r["emotion"]] += 1
        ratings_dist[r["rating"]] += 1

    sentiment_trend = [{"week": f"Week-{i+1}", "avg": round(random.uniform(0.4, 0.9), 2)} for i in range(6)]

    return {
        "metadata": {"total_reviews": total_reviews},
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": round(random.uniform(0, 100), 2),
        },
        "visualizations": {
            "emotions": emotions_count,
            "sentiment_trend": sentiment_trend,
            "ratings": ratings_dist,
        },
    }

@router.get("/api/revenue")
async def get_revenue(company_id: str):
    if company_id not in reviews_db:
        raise HTTPException(status_code=404, detail="Company not found")
    return {
        "risk_percent": round(random.uniform(0, 100), 2),
        "impact": random.choice(["Low", "Medium", "High"]),
        "loss_estimate": round(random.uniform(1000, 10000), 2),
    }

@router.post("/api/reviews/ingest/{company_id}")
async def ingest_reviews(company_id: str):
    if company_id not in reviews_db:
        raise HTTPException(status_code=404, detail="Company not found")
    new_reviews = [
        {
            "rating": random.randint(1, 5),
            "sentiment": random.uniform(0, 1),
            "emotion": random.choice(["Happy", "Angry", "Neutral"]),
        }
        for _ in range(random.randint(5, 20))
    ]
    reviews_db[company_id].extend(new_reviews)
    return {"status": "success", "reviews_added": len(new_reviews)}

# Health check
@router.get("/health")
async def health_check():
    return {"status": "ok"}
