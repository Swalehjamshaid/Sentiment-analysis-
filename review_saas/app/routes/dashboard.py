# filename: app/routes/dashboard.py
# ==========================================================
# FULLY INTEGRATED DASHBOARD (FRONTEND + BACKEND MATCHED)
# ==========================================================

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from datetime import datetime
from collections import defaultdict, Counter, deque
from io import BytesIO
import re

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from app.core.db import get_session
from app.core.models import Review, Competitor

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ==========================================================
# CHAT MEMORY
# ==========================================================
CHAT_MEMORY = {}
MAX_MEMORY = 10

def remember(company_id, role, message):
    mem = CHAT_MEMORY.setdefault(company_id, [])
    mem.append({"role": role, "message": message})
    if len(mem) > MAX_MEMORY:
        mem.pop(0)

def recall(company_id):
    return CHAT_MEMORY.get(company_id, [])

# ==========================================================
# KEYWORD EXTRACTION (FOR YOUR FRONTEND)
# ==========================================================
def extract_keywords(reviews, top_n=20):
    text = " ".join([r.review_text or "" for r in reviews]).lower()
    words = re.findall(r'\b[a-z]{4,}\b', text)

    stopwords = {
        "this","that","with","have","very","from","they","their","there",
        "about","would","could","should","been","were","your","what"
    }

    words = [w for w in words if w not in stopwords]
    freq = Counter(words).most_common(top_n)

    return [{"text": w, "value": c} for w, c in freq]

# ==========================================================
# CORE ANALYTICS ENGINE
# ==========================================================
def compute_analytics(reviews):
    if not reviews:
        return None

    total = len(reviews)
    ratings = []
    sentiments = []

    rating_dist = {1:0,2:0,3:0,4:0,5:0}
    emotions = {"Positive":0,"Neutral":0,"Negative":0}

    daily = defaultdict(list)
    monthly = defaultdict(list)

    responded = 0
    complaints = 0

    for r in reviews:
        rating = r.rating or 0
        sentiment = r.sentiment_score or 0

        ratings.append(rating)
        sentiments.append(sentiment)

        if rating in rating_dist:
            rating_dist[rating] += 1

        # Emotion classification
        if sentiment >= 0.25:
            emotions["Positive"] += 1
        elif sentiment <= -0.25:
            emotions["Negative"] += 1
        else:
            emotions["Neutral"] += 1

        # Time grouping
        if r.google_review_time:
            d = r.google_review_time.strftime("%Y-%m-%d")
            m = r.google_review_time.strftime("%b %Y")
            daily[d].append(rating)
            monthly[m].append(sentiment)

        # Response + complaints
        if getattr(r, "review_reply_text", None):
            responded += 1
        if getattr(r, "is_complaint", False):
            complaints += 1

    avg_rating = round(sum(ratings)/len(ratings), 2)
    reputation = int((avg_rating/5)*100)

    # Trend smoothing (7-day rolling)
    trend = []
    window = deque(maxlen=7)

    for d in sorted(daily):
        avg = sum(daily[d]) / len(daily[d])
        window.append(avg)
        trend.append({
            "week": d,
            "avg": round(sum(window)/len(window), 2)
        })

    # Keywords
    keywords = extract_keywords(reviews)

    return {
        "total_reviews": total,
        "average_rating": avg_rating,
        "reputation_score": reputation,
        "ratings": rating_dist,
        "emotions": emotions,
        "sentiment_trend": trend,
        "response_rate": round((responded/total)*100, 2),
        "complaint_ratio": round((complaints/total)*100, 2),
        "keywords": keywords
    }

# ==========================================================
# MAIN INSIGHTS (MATCHES YOUR FRONTEND EXACTLY)
# ==========================================================
@router.get("/ai/insights")
async def insights(
    company_id: int,
    start: str,
    end: str,
    session: AsyncSession = Depends(get_session)
):
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except:
        return _empty()

    res = await session.execute(
        select(Review).where(
            and_(
                Review.company_id == company_id,
                or_(
                    Review.google_review_time.is_(None),
                    and_(
                        Review.google_review_time >= start_dt,
                        Review.google_review_time <= end_dt
                    )
                )
            )
        )
    )

    reviews = res.scalars().all()
    data = compute_analytics(reviews)

    if not data:
        return _empty()

    return {
        "metadata": {"total_reviews": data["total_reviews"]},
        "kpis": {
            "average_rating": data["average_rating"],
            "reputation_score": data["reputation_score"]
        },
        "visualizations": {
            "ratings": data["ratings"],
            "emotions": data["emotions"],
            "sentiment_trend": data["sentiment_trend"],
            "keywords": data["keywords"]   # ✅ IMPORTANT (frontend uses this)
        }
    }

# ==========================================================
# CHATBOT (CONNECTED TO FRONTEND)
# ==========================================================
@router.get("/chatbot/explain/{company_id}")
async def chatbot(company_id: int, question: str, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    data = compute_analytics(res.scalars().all())

    if not data:
        return {"answer": "No data available."}

    q = question.lower()

    if "rating" in q:
        ans = f"Your average rating is {data['average_rating']}."
    elif "sentiment" in q:
        top = max(data["emotions"], key=data["emotions"].get)
        ans = f"Customer sentiment is mostly {top}."
    elif "improve" in q:
        ans = "Focus on complaints and low ratings to improve performance."
    else:
        ans = "Your business is performing steadily. Monitor trends for growth."

    remember(company_id, "user", question)
    remember(company_id, "ai", ans)

    return {"answer": ans, "memory": recall(company_id)}

# ==========================================================
# REVENUE RISK (MATCHES FRONTEND)
# ==========================================================
@router.get("/revenue")
async def revenue(company_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(
        select(func.avg(Review.rating)).where(Review.company_id == company_id)
    )
    avg = res.scalar() or 0

    if avg >= 4:
        return {"risk_percent": 10, "impact": "Low"}
    elif avg >= 3:
        return {"risk_percent": 40, "impact": "Medium"}
    else:
        return {"risk_percent": 80, "impact": "High"}

# ==========================================================
# PDF REPORT (FIXED FOR PRODUCTION)
# ==========================================================
@router.get("/executive-report/pdf/{company_id}")
async def pdf(company_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    data = compute_analytics(res.scalars().all())

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()

    elements = []

    elements.append(Paragraph("Executive Report", styles["Title"]))
    elements.append(Spacer(1, 10))

    if data:
        elements.append(Paragraph(f"Avg Rating: {data['average_rating']}", styles["Normal"]))
        elements.append(Paragraph(f"Reputation Score: {data['reputation_score']}", styles["Normal"]))
        elements.append(Paragraph(f"Response Rate: {data['response_rate']}%", styles["Normal"]))

    doc.build(elements)
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="application/pdf")

# ==========================================================
# EMPTY RESPONSE
# ==========================================================
def _empty():
    return {
        "metadata": {"total_reviews": 0},
        "kpis": {"average_rating": 0, "reputation_score": 0},
        "visualizations": {
            "ratings": {1:0,2:0,3:0,4:0,5:0},
            "emotions": {"Positive":0,"Neutral":0,"Negative":0},
            "sentiment_trend": [],
            "keywords": []
        }
    }
