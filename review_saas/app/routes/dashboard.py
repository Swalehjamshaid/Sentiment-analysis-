# dashboard.py

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict
import random
from datetime import datetime, timedelta
import os

app = FastAPI(title="Review Intelligence AI Dashboard")

# ===============================
# CORS Middleware
# ===============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================
# SAFE STATIC MOUNT (NO CRASH)
# ===============================
STATIC_DIR = "static"

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    print("⚠️ WARNING: 'static' directory not found. Skipping static mount.")

# ===============================
# SAFE TEMPLATE PATH
# ===============================
TEMPLATE_PATH = os.path.join("templates", "dashboard.html")

# ===============================
# In-Memory Mock Database
# ===============================
companies_db = [
    {"id": "1", "name": "TechMart", "place_id": "abc123", "address": "123 Tech St"},
    {"id": "2", "name": "Cafe Deluxe", "place_id": "def456", "address": "456 Coffee Rd"},
]

reviews_db = {
    "1": [
        {
            "rating": random.randint(1, 5),
            "sentiment": random.uniform(0, 1),
            "emotion": random.choice(["Happy", "Angry", "Neutral"]),
        }
        for _ in range(120)
    ],
    "2": [
        {
            "rating": random.randint(1, 5),
            "sentiment": random.uniform(0, 1),
            "emotion": random.choice(["Happy", "Angry", "Neutral"]),
        }
        for _ in range(80)
    ],
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
# HTML Endpoint (SAFE)
# ===============================
@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    if not os.path.exists(TEMPLATE_PATH):
        return HTMLResponse(
            "<h1>Dashboard UI not found</h1><p>Please upload templates/dashboard.html</p>"
        )

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
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

    companies_db.append(
        {
            "id": new_id,
            "name": company.name,
            "place_id": company.place_id,
            "address": company.address,
        }
    )

    reviews_db[new_id] = []

    return JSONResponse({"status": "success", "company_id": new_id})


# ===============================
# API: Dashboard AI Insights
# ===============================
@app.get("/api/dashboard/ai/insights")
async def get_ai_insights(company_id: str, start: str = None, end: str = None):

    if company_id not in reviews_db:
        raise HTTPException(status_code=404, detail="Company not found")

    try:
        start_date = (
            datetime.strptime(start, "%Y-%m-%d")
            if start
            else datetime.now() - timedelta(days=30)
        )
        end_date = (
            datetime.strptime(end, "%Y-%m-%d") if end else datetime.now()
        )
    except:
        raise HTTPException(status_code=400, detail="Invalid date format (YYYY-MM-DD)")

    reviews = reviews_db[company_id]

    total_reviews = len(reviews)

    avg_rating = (
        round(sum(r["rating"] for r in reviews) / total_reviews, 2)
        if total_reviews
        else 0
    )

    emotions_count = {"Happy": 0, "Angry": 0, "Neutral": 0}
    sentiment_trend = []
    ratings_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    for r in reviews:
        emotions_count[r["emotion"]] += 1
        ratings_dist[r["rating"]] += 1

    # Mock sentiment trend (weekly)
    for i in range(6):
        sentiment_trend.append(
            {"week": f"Week-{i+1}", "avg": round(random.uniform(0.4, 0.9), 2)}
        )

    data = {
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

    return data


# ===============================
# API: Revenue Risk
# ===============================
@app.get("/api/dashboard/revenue")
async def get_revenue(company_id: str):

    if company_id not in reviews_db:
        raise HTTPException(status_code=404, detail="Company not found")

    return {
        "risk_percent": round(random.uniform(0, 100), 2),
        "impact": random.choice(["Low", "Medium", "High"]),
        "loss_estimate": round(random.uniform(1000, 10000), 2),
    }


# ===============================
# API: Ingest Reviews
# ===============================
@app.post("/api/reviews/ingest/{company_id}")
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


# ===============================
# API: AI Chat
# ===============================
@app.post("/chatbot/chat")
async def chatbot_chat(chat: ChatMessage):

    responses = [
        "Customers are generally satisfied.",
        "Sentiment trend is improving.",
        "Focus on reducing delivery time.",
        "Your top product is performing very well.",
    ]

    return {"answer": random.choice(responses)}


# ===============================
# HEALTH CHECK (IMPORTANT FOR RAILWAY)
# ===============================
@app.get("/health")
async def health_check():
    return {"status": "ok"}


# ===============================
# RUN LOCAL
# ===============================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
