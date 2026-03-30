import random
from datetime import datetime, timezone
from typing import Optional, List
import logging

from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from starlette.templating import Jinja2Templates
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.core.db import get_session
from app.core.models import Review, Company
from app.chatbot import generate_ai_response  # async AI logic

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/dashboard", tags=["dashboard"])
vader_analyzer = SentimentIntensityAnalyzer()
logger = logging.getLogger("dashboard")
logger.setLevel(logging.INFO)

# ---------------------------------------------------------
# AUTH
# ---------------------------------------------------------
def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

# ---------------------------------------------------------
# 1. DASHBOARD PAGE
# ---------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})

# ---------------------------------------------------------
# 2. REVENUE API
# ---------------------------------------------------------
@router.get("/revenue")
async def revenue_api(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    result = await session.execute(select(Review).where(Review.company_id == company_id))
    reviews: List[Review] = result.scalars().all()

    if not reviews:
        return JSONResponse({
            "company_id": company_id,
            "risk_percent": 10,
            "impact": "Low",
            "reputation_score": 75,
            "total_reviews": 0,
            "negative_percent": 0,
            "last_updated": datetime.now(timezone.utc).isoformat()
        })

    total = len(reviews)
    avg_rating = round(sum(r.rating for r in reviews) / total, 1)
    negative = sum(
        1 for r in reviews if r.text and vader_analyzer.polarity_scores(r.text)['compound'] < -0.05
    )
    negative_percent = round((negative / total) * 100, 1)
    risk_percent = max(5, min(48, int(negative_percent * 1.3 + (5.0 - avg_rating) * 12)))
    impact = "High" if risk_percent > 32 else "Medium" if risk_percent > 16 else "Low"
    reputation_score = max(55, min(97, int(avg_rating * 19.5)))

    return JSONResponse({
        "company_id": company_id,
        "risk_percent": risk_percent,
        "impact": impact,
        "reputation_score": reputation_score,
        "total_reviews": total,
        "negative_percent": negative_percent,
        "last_updated": datetime.now(timezone.utc).isoformat()
    })

# ---------------------------------------------------------
# 3. AI INSIGHTS (All reviews, analytics)
# ---------------------------------------------------------
@router.get("/ai/insights")
async def ai_insights(
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    # Fetch all reviews dynamically
    query = select(Review).where(Review.company_id == company_id)
    if start:
        query = query.where(Review.created_at >= datetime.fromisoformat(start))
    if end:
        query = query.where(Review.created_at <= datetime.fromisoformat(end))
    result = await session.execute(query)
    reviews: List[Review] = result.scalars().all()

    total = len(reviews)
    if total == 0:
        return JSONResponse({
            "metadata": {"company_id": company_id, "total_reviews": 0, "generated_at": datetime.now(timezone.utc).isoformat()},
            "kpis": {"average_rating": 0, "reputation_score": 70, "response_rate": 60},
            "visualizations": {
                "emotions": {"Positive": 50, "Neutral": 30, "Negative": 20},
                "sentiment_trend": [{"week": f"W{i}", "avg": 4.0} for i in range(1, 9)],
                "ratings": {i: 0 for i in range(1,6)}
            },
            "ai_recommendations": ["No data yet. Click Sync Live Data."]
        })

    # KPI Calculations
    avg_rating = round(sum(r.rating for r in reviews)/total,1)
    pos = neg = neu = 0
    ratings = {i: 0 for i in range(1,6)}

    for r in reviews:
        ratings[int(r.rating)] += 1 if 1 <= int(r.rating) <= 5 else 0
        if r.text:
            score = vader_analyzer.polarity_scores(r.text)['compound']
            if score >= 0.05:
                pos += 1
            elif score <= -0.05:
                neg += 1
            else:
                neu += 1
        else:
            neu += 1
    total_map = pos + neg + neu or 1

    # Visualizations
    visualizations = {
        "emotions": {
            "Positive": round(pos*100/total_map),
            "Neutral": round(neu*100/total_map),
            "Negative": round(neg*100/total_map)
        },
        "sentiment_trend": [
            {"week": f"W{i}", "avg": round(random.uniform(3.8,4.7),1)}
            for i in range(1, 9)
        ],
        "ratings": ratings
    }

    # AI Recommendations
    ai_recommendations = [
        f"Avg rating {avg_rating} → Improve response speed",
        "Respond to negative reviews quickly",
        "Leverage top-rated experiences in marketing"
    ]

    return JSONResponse({
        "metadata": {"company_id": company_id, "total_reviews": total, "generated_at": datetime.now(timezone.utc).isoformat()},
        "kpis": {"average_rating": avg_rating, "reputation_score": int(avg_rating*19.8), "response_rate": 65},
        "visualizations": visualizations,
        "ai_recommendations": ai_recommendations,
        "reviews": [{"id": r.id, "rating": r.rating, "text": r.text} for r in reviews]  # <-- all reviews
    })

# ---------------------------------------------------------
# 4. AI CHAT (Improved)
# ---------------------------------------------------------
@router.post("/chat")
async def chat_api(request: Request, session: AsyncSession = Depends(get_session), current_user: dict = Depends(get_current_user)):
    try:
        body = await request.json()
        company_id = body.get("company_id")
        msg = body.get("message","").strip()

        if not msg or not company_id:
            return JSONResponse({"answer": "AI Expert: Please select a business and ask a question."})

        company = (await session.execute(select(Company).where(Company.id == company_id))).scalar_one_or_none()
        name = company.name if company else "this business"

        reviews = (await session.execute(select(Review).where(Review.company_id == company_id))).scalars().all()
        context = [r.text for r in reviews[-100:]]  # last 100 reviews for AI context
        answer = await generate_ai_response(msg, context)

        return JSONResponse({"answer": answer, "timestamp": datetime.now(timezone.utc).isoformat()})
    except Exception as e:
        logger.exception("Chatbot error")
        return JSONResponse({"answer": "AI Expert: I'm having trouble retrieving a response."})
