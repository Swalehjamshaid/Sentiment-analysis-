import logging
from datetime import datetime, timezone
from collections import defaultdict, Counter

from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from starlette.templating import Jinja2Templates

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import CountVectorizer
import plotly.graph_objs as go
import random

from app.core.db import get_session
from app.core.models import Review, Company

# ----------------------------
# Logging
# ----------------------------
logger = logging.getLogger("dashboard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ----------------------------
# Templates & Router
# ----------------------------
templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

vader_analyzer = SentimentIntensityAnalyzer()

# ----------------------------
# Auth Helper
# ----------------------------
def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

# ----------------------------
# Dashboard Home
# ----------------------------
@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})

# ----------------------------
# Helper: Process Reviews
# ----------------------------
async def fetch_reviews(session: AsyncSession, company_id: int):
    result = await session.execute(select(Review).where(Review.company_id == company_id))
    return result.scalars().all()

def analyze_sentiments(reviews):
    pos = neg = neu = 0
    sentiments = []
    ratings = {1:0, 2:0, 3:0, 4:0, 5:0}
    monthly_data = defaultdict(list)

    for r in reviews:
        # Ratings
        rating = int(r.rating) if 1 <= int(r.rating) <= 5 else 0
        if rating:
            ratings[rating] += 1
        
        # Sentiment
        if r.text:
            score = vader_analyzer.polarity_scores(r.text)["compound"]
            sentiments.append(score)
            if score >= 0.05: pos += 1
            elif score <= -0.05: neg += 1
            else: neu += 1
        else:
            sentiments.append(0)
            neu += 1
        
        # Month-wise
        month = r.created_at.strftime("%Y-%m")
        monthly_data[month].append(r.rating)

    total_reviews = len(reviews)
    avg_rating = round(sum(r.rating for r in reviews)/total_reviews,1) if total_reviews else 0
    sentiment_distribution = {
        "Positive": round(pos*100/total_reviews,1) if total_reviews else 0,
        "Neutral": round(neu*100/total_reviews,1) if total_reviews else 0,
        "Negative": round(neg*100/total_reviews,1) if total_reviews else 0
    }

    # Month-wise average rating
    monthly_avg = {month: round(sum(vals)/len(vals),2) for month, vals in monthly_data.items()}

    return {
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "ratings": ratings,
        "sentiment_distribution": sentiment_distribution,
        "monthly_avg": monthly_avg,
        "sentiments": sentiments
    }

# ----------------------------
# KPI API
# ----------------------------
@router.get("/kpi")
async def dashboard_kpi(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    try:
        reviews = await fetch_reviews(session, company_id)
        analysis = analyze_sentiments(reviews)

        risk_percent = max(5, min(50, int((100-analysis["avg_rating"]*20) + analysis["sentiment_distribution"]["Negative"])))
        impact = "High" if risk_percent>32 else "Medium" if risk_percent>16 else "Low"
        reputation_score = max(55, min(100, int(analysis["avg_rating"]*20)))

        return JSONResponse({
            "company_id": company_id,
            "total_reviews": analysis["total_reviews"],
            "average_rating": analysis["avg_rating"],
            "ratings": analysis["ratings"],
            "sentiment_distribution": analysis["sentiment_distribution"],
            "monthly_avg_rating": analysis["monthly_avg"],
            "risk_percent": risk_percent,
            "impact": impact,
            "reputation_score": reputation_score
        })
    except Exception as e:
        logger.exception("KPI API failed")
        return JSONResponse({"error":"Failed to fetch KPI"}, status_code=500)

# ----------------------------
# Month-wise Plotly Chart API
# ----------------------------
@router.get("/charts")
async def dashboard_charts(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    try:
        reviews = await fetch_reviews(session, company_id)
        analysis = analyze_sentiments(reviews)

        # Ratings Distribution Bar
        ratings_bar = go.Figure([go.Bar(
            x=list(analysis["ratings"].keys()),
            y=list(analysis["ratings"].values()),
            marker_color='indianred'
        )])
        ratings_bar.update_layout(title="Ratings Distribution", xaxis_title="Rating", yaxis_title="Count")
        ratings_chart = ratings_bar.to_json()

        # Sentiment Pie
        sentiment_pie = go.Figure([go.Pie(
            labels=list(analysis["sentiment_distribution"].keys()),
            values=list(analysis["sentiment_distribution"].values()),
            hole=0.4
        )])
        sentiment_pie.update_layout(title="Sentiment Distribution")
        sentiment_chart = sentiment_pie.to_json()

        # Month-wise Rating Trend
        months = list(analysis["monthly_avg"].keys())
        avg_ratings = list(analysis["monthly_avg"].values())
        trend_line = go.Figure([go.Scatter(
            x=months,
            y=avg_ratings,
            mode="lines+markers",
            line=dict(color='royalblue', width=3)
        )])
        trend_line.update_layout(title="Month-wise Average Rating", xaxis_title="Month", yaxis_title="Average Rating")
        trend_chart = trend_line.to_json()

        return JSONResponse({
            "ratings_chart": ratings_chart,
            "sentiment_chart": sentiment_chart,
            "trend_chart": trend_chart
        })

    except Exception as e:
        logger.exception("Chart API failed")
        return JSONResponse({"error":"Failed to generate charts"}, status_code=500)

# ----------------------------
# AI Chatbot
# ----------------------------
@router.post("/chat")
async def dashboard_chat(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    try:
        body = await request.json()
        company_id = body.get("company_id")
        message = body.get("message", "").strip()

        if not message or not company_id:
            return JSONResponse({"answer":"AI: Please select a company and ask a question."})

        reviews = await fetch_reviews(session, company_id)
        if not reviews:
            return JSONResponse({"answer":"AI: No data available for this company. Please sync reviews."})

        avg_rating = round(sum(r.rating for r in reviews)/len(reviews),1)
        neg_count = len([r for r in reviews if r.rating<3])
        risk_pct = int((neg_count/len(reviews))*100)

        msg_lower = message.lower()
        if "rating" in msg_lower:
            answer = f"AI: Average rating is {avg_rating}/5 based on {len(reviews)} reviews."
        elif "risk" in msg_lower:
            level = "High" if risk_pct>20 else "Medium" if risk_pct>10 else "Low"
            answer = f"AI: Revenue risk is {level} ({risk_pct}% negative feedback)."
        elif "improve" in msg_lower:
            bad_review = next((r.text for r in reviews if r.rating<3 and r.text), "customer experience")
            answer = f"AI: Improve performance by addressing: '{bad_review[:80]}'"
        else:
            answer = f"AI: {len(reviews)} reviews analyzed. Focus on improving customer satisfaction."

        return JSONResponse({"answer":answer})
    except Exception as e:
        logger.exception("AI Chat failed")
        return JSONResponse({"answer":"AI: Sorry, I cannot process this request right now."})
