from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
import asyncio
import random
from datetime import datetime

# ==========================
# APP INIT
# ==========================
app = FastAPI(title="Review Intelligence AI Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files if needed (CSS/JS/Images)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================
# MOCK DATABASE / MODELS
# ==========================
class Company(BaseModel):
    id: int
    name: str
    place_id: str
    address: str

class Review(BaseModel):
    id: int
    company_id: int
    rating: int
    sentiment: float
    emotion: str
    date: str

# In-memory storage for demonstration
COMPANIES = [
    Company(id=1, name="Cafe Blue", place_id="abc123", address="123 Blue St"),
    Company(id=2, name="Tech Shop", place_id="def456", address="456 Tech Ave"),
]
REVIEWS = []

# ==========================
# DASHBOARD ROUTE
# ==========================
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    with open("templates/dashboard.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

# ==========================
# COMPANIES API
# ==========================
@app.get("/api/companies", response_model=List[Company])
async def get_companies():
    return COMPANIES

@app.post("/api/companies", response_model=Company)
async def add_company(company: Company):
    new_id = max([c.id for c in COMPANIES] + [0]) + 1
    new_company = Company(id=new_id, **company.dict())
    COMPANIES.append(new_company)
    return new_company

# ==========================
# AI INSIGHTS & KPI API
# ==========================
@app.get("/api/ai/insights")
async def ai_insights(company_id: int, start: str = "2023-01-01", end: str = None):
    end = end or datetime.today().strftime("%Y-%m-%d")
    # Mock KPIs & visualizations
    data = {
        "metadata": {"total_reviews": random.randint(50, 500)},
        "kpis": {
            "benchmark": {"your_avg": round(random.uniform(3.0, 5.0), 2)},
            "reputation_score": round(random.uniform(50, 100), 2)
        },
        "visualizations": {
            "emotions": {"Happy": random.randint(10,50), "Angry": random.randint(0,10), "Sad": random.randint(0,5)},
            "sentiment_trend": [{"week": f"W{i}", "avg": round(random.uniform(2.5, 5.0),2)} for i in range(1,13)],
            "ratings": {str(i): random.randint(0,50) for i in range(1,6)}
        }
    }
    return JSONResponse(content=data)

# ==========================
# REVENUE RISK API
# ==========================
@app.get("/api/dashboard/revenue")
async def revenue_risk(company_id: int):
    data = {
        "risk_percent": random.randint(5,50),
        "impact": random.choice(["Low","Medium","High"]),
    }
    return JSONResponse(content=data)

# ==========================
# AI CHAT API
# ==========================
@app.post("/api/dashboard/chat")
async def chat(company_id: int, request: Request):
    payload = await request.json()
    question = payload if isinstance(payload, str) else str(payload)
    # Mock AI response
    answers = [
        "Focus on improving your 4★ reviews.",
        "Customer sentiment is trending positive.",
        "Consider addressing negative feedback quickly."
    ]
    return {"answer": random.choice(answers)}

# ==========================
# SYNC REVIEWS / INGEST
# ==========================
@app.post("/api/reviews/ingest/{company_id}")
async def ingest_reviews(company_id: int):
    # Placeholder for your Playwright or SerpAPI logic
    new_reviews = random.randint(5,20)
    for _ in range(new_reviews):
        REVIEWS.append(
            Review(
                id=len(REVIEWS)+1,
                company_id=company_id,
                rating=random.randint(1,5),
                sentiment=round(random.uniform(1.0,5.0),2),
                emotion=random.choice(["Happy","Sad","Angry"]),
                date=datetime.today().strftime("%Y-%m-%d")
            )
        )
    return {"reviews_count": new_reviews}

# ==========================
# RUN APP
# ==========================
# Use: uvicorn dashboard:app --reload
