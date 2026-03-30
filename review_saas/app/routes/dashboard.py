# dashboard.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict
import random
from datetime import datetime, timedelta

app = FastAPI(title="Review Intelligence AI Dashboard")

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static directory if needed (JS/CSS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ===============================
# In-Memory Mock Database
# ===============================
companies_db = [
    {"id": "1", "name": "TechMart", "place_id": "abc123", "address": "123 Tech St"},
    {"id": "2", "name": "Cafe Deluxe", "place_id": "def456", "address": "456 Coffee Rd"},
]

reviews_db = {
    "1": [
        {"rating": random.randint(1,5), "sentiment": random.uniform(0,1), "emotion": random.choice(["Happy","Angry","Neutral"]) } 
        for _ in range(120)
    ],
    "2": [
        {"rating": random.randint(1,5), "sentiment": random.uniform(0,1), "emotion": random.choice(["Happy","Angry","Neutral"]) } 
        for _ in range(80)
    ]
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
# HTML Endpoint
# ===============================
@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    with open("templates/dashboard.html", "r") as f:
        return HTMLResponse(f.read())

# ===============================
# API: Companies
# ===============================
@app.get("/api/companies")
async def get_companies():
    return {"companies": companies_db}

@app.post("/api/companies")
async def add_company(company: CompanyCreate):
    new_id = str(len(companies_db) + 1)
    companies_db.append({
        "id": new_id,
        "name": company.name,
        "place_id": company.place_id,
        "address": company.address
    })
    reviews_db[new_id] = []
    return JSONResponse({"status": "success", "company_id": new_id})

# ===============================
# API: Dashboard AI Insights
# ===============================
@app.get("/api/dashboard/ai/insights")
async def get_ai_insights(company_id: str, start: str = None, end: str = None):
    if company_id not in reviews_db:
        raise HTTPException(status_code=404, detail="Company not found")

    start_date = datetime.strptime(start, "%Y-%m-%d") if start else datetime.now() - timedelta(days=30)
    end_date = datetime.strptime(end, "%Y-%m-%d") if end else datetime.now()

    reviews = reviews_db[company_id]

    total_reviews = len(reviews)
    avg_rating = round(sum(r["rating"] for r in reviews)/total_reviews, 2) if total_reviews else 0

    # Mock sentiment & emotions
    emotions_count = {"Happy":0,"Angry":0,"Neutral":0}
    sentiment_trend = []
    ratings_dist = {1:0,2:0,3:0,4:0,5:0}
    
    for r in reviews:
        emotions_count[r["emotion"]] += 1
        ratings_dist[r["rating"]] += 1

    # Mock weekly sentiment trend
    for i in range(6):
        sentiment_trend.append({"week": f"Week-{i+1}", "avg": round(random.uniform(0.4,0.9),2)})

    data = {
        "metadata": {"total_reviews": total_reviews},
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": round(random.uniform(0,100),2)
        },
        "visualizations": {
            "emotions": emotions_count,
            "sentiment_trend": sentiment_trend,
            "ratings": ratings_dist
        }
    }
    return data

# ===============================
# API: Revenue Risk
# ===============================
@app.get("/api/dashboard/revenue")
async def get_revenue(company_id: str):
    return {
        "risk_percent": round(random.uniform(0,100),2),
        "impact": random.choice(["Low","Medium","High"]),
        "loss_estimate": round(random.uniform(1000,10000),2)
    }

# ===============================
# API: Ingest Reviews
# ===============================
@app.post("/api/reviews/ingest/{company_id}")
async def ingest_reviews(company_id: str):
    if company_id not in reviews_db:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Simulate ingest
    new_reviews = [
        {"rating": random.randint(1,5), "sentiment": random.uniform(0,1), "emotion": random.choice(["Happy","Angry","Neutral"])}
        for _ in range(random.randint(5,20))
    ]
    reviews_db[company_id].extend(new_reviews)
    return {"status": "success", "reviews_count": len(new_reviews)}

# ===============================
# API: AI Chat
# ===============================
@app.post("/chatbot/chat")
async def chatbot_chat(chat: ChatMessage):
    # Simple mock AI response
    responses = [
        "Our customers are mostly happy.",
        "Average sentiment is improving week by week.",
        "Consider improving your service speed.",
        "Top-rated product is your coffee."
    ]
    return {"answer": random.choice(responses)}

# ===============================
# Run (for dev purposes)
# ===============================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
