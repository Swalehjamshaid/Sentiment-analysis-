# File: app/routes/dashboard.py
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import random
from datetime import datetime, timedelta

from app.core.db import get_session
from app.core.models import User, Company, Review
from starlette.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# -------------------------------
# Helper: Get Current User
# -------------------------------
def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


# -------------------------------
# Dashboard Home Page
# -------------------------------
@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "page_title": "Dashboard"
        }
    )


# -------------------------------
# Revenue Risk API - Improved
# -------------------------------
@router.get("/revenue")
async def revenue_api(
    company_id: int = Query(..., description="Company ID"),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    # TODO: In production, verify that user has access to this company
    
    # For now, returning realistic dummy data
    risk_percent = random.randint(8, 42)
    
    return JSONResponse({
        "company_id": company_id,
        "risk_percent": risk_percent,
        "impact": "High" if risk_percent > 30 else "Medium" if risk_percent > 15 else "Low",
        "reputation_score": random.randint(45, 98),
        "last_updated": datetime.utcnow().isoformat(),
        "trend": random.choice(["improving", "declining", "stable"]),
        "factors": [
            "Recent negative reviews",
            "Response rate below 40%",
            "Competitor outperforming in key areas"
        ][:random.randint(1, 3)]
    })


# -------------------------------
# AI Chat API - Improved
# -------------------------------
@router.post("/chat")
async def chat_api(
    company_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    try:
        body = await request.json()
        user_message = body.get("message", "")
        
        if not user_message or len(user_message.strip()) < 2:
            raise HTTPException(status_code=400, detail="Message too short")

        # Simulate AI thinking time + smarter response
        responses = [
            f"Based on recent reviews for company {company_id}, customers are particularly happy with your service speed.",
            "I noticed a spike in 'delivery delay' complaints in the last 7 days. Would you like me to analyze this further?",
            "Your overall sentiment score has improved by 12% this month. Great work on customer support!",
            "Recommendation: Increase response rate to reviews. Currently at ~35%, best performers maintain >70%.",
            "Top 3 issues mentioned recently: 1) Pricing transparency 2) Wait times 3) Product quality consistency."
        ]

        return JSONResponse({
            "answer": random.choice(responses),
            "company_id": company_id,
            "timestamp": datetime.utcnow().isoformat(),
            "confidence": round(random.uniform(0.75, 0.98), 2)
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to process chat request")


# -------------------------------
# AI Insights API - Much Improved
# -------------------------------
@router.get("/ai/insights")
async def ai_insights(
    company_id: int = Query(..., description="Company ID"),
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    # TODO: Add real database queries in production
    # For now, generating rich, realistic dummy data

    total_reviews = random.randint(245, 1240)

    return JSONResponse({
        "metadata": {
            "company_id": company_id,
            "total_reviews": total_reviews,
            "date_range": {
                "start": start or (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d"),
                "end": end or datetime.utcnow().strftime("%Y-%m-%d")
            },
            "generated_at": datetime.utcnow().isoformat()
        },
        "kpis": {
            "average_rating": round(random.uniform(3.8, 4.7), 1),
            "benchmark": {
                "your_avg": round(random.uniform(3.8, 4.7), 2),
                "industry_avg": round(random.uniform(3.9, 4.4), 2),
                "top_performers": round(random.uniform(4.5, 4.9), 2)
            },
            "reputation_score": random.randint(68, 96),
            "response_rate": round(random.uniform(35, 92), 1),
            "review_growth": random.randint(-15, 45)
        },
        "visualizations": {
            "emotions": {
                "Positive": random.randint(65, 89),
                "Neutral": random.randint(8, 25),
                "Negative": random.randint(3, 18)
            },
            "sentiment_trend": [
                {"week": f"W{i}", "avg": round(random.uniform(3.6, 4.8), 1)}
                for i in range(1, 9)
            ],
            "ratings_distribution": {
                1: random.randint(2, 15),
                2: random.randint(8, 35),
                3: random.randint(25, 80),
                4: random.randint(60, 180),
                5: random.randint(90, 320)
            },
            "monthly_trend": [
                {
                    "month": (datetime.utcnow() - timedelta(days=30*i)).strftime("%b"),
                    "reviews": random.randint(40, 180),
                    "avg_rating": round(random.uniform(3.7, 4.8), 1)
                }
                for i in range(6)
            ]
        },
        "recommendations": [
            "Improve response time to negative reviews (currently 48 hours average)",
            "Focus on 'Value for Money' mentions in marketing",
            "Consider loyalty program to boost 5-star reviews"
        ]
    })


# Optional: Add a companies list endpoint for the dashboard sidebar
@router.get("/companies")
async def get_user_companies(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    # In real implementation, query companies user has access to
    return JSONResponse({
        "companies": [
            {"id": 1, "name": "Acme Corp", "rating": 4.3},
            {"id": 2, "name": "TechFlow Solutions", "rating": 4.7},
            {"id": 3, "name": "GreenLife Stores", "rating": 3.9}
        ]
    })
