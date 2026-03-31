from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from datetime import datetime
from collections import defaultdict, deque
from io import BytesIO

from reportlab.pdfgen import canvas

from app.core.db import get_session
from app.core.models import Review, Competitor

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# -------------------------------------------------------------------
# SIMPLE IN‑MEMORY CHAT MEMORY (per company)
# -------------------------------------------------------------------
CHAT_MEMORY = {}
MAX_MEMORY = 10

def remember(company_id, role, message):
    mem = CHAT_MEMORY.setdefault(company_id, [])
    mem.append({"role": role, "message": message})
    if len(mem) > MAX_MEMORY:
        mem.pop(0)

def recall(company_id):
    return CHAT_MEMORY.get(company_id, [])

# -------------------------------------------------------------------
# SHARED ANALYTICS ENGINE
# -------------------------------------------------------------------
def compute_analytics(reviews):
    total = len(reviews)
    if total == 0:
        return None

    ratings = []
    sentiments = []
    emotions = {"Positive": 0, "Neutral": 0, "Negative": 0}
    rating_dist = {1:0,2:0,3:0,4:0,5:0}
    daily = defaultdict(list)
    monthly = defaultdict(list)

    responded = 0
    complaints = 0

    for r in reviews:
        if isinstance(r.rating, (int, float)):
            ratings.append(r.rating)
        if isinstance(r.sentiment_score, (int, float)):
            sentiments.append(r.sentiment_score)

        if r.rating in rating_dist:
            rating_dist[r.rating] += 1

        score = r.sentiment_score or 0.0
        if score >= 0.25:
            emotions["Positive"] += 1
        elif score <= -0.25:
            emotions["Negative"] += 1
        else:
            emotions["Neutral"] += 1

        if r.google_review_time:
            day = r.google_review_time.strftime("%Y-%m-%d")
            month = r.google_review_time.strftime("%b %Y")
            daily[day].append(r.rating or 0)
            monthly[month].append(score)

        if getattr(r, "review_reply_text", None):
            responded += 1
        if getattr(r, "is_complaint", False):
            complaints += 1

    avg_rating = round(sum(ratings)/len(ratings), 2) if ratings else 0
    reputation_score = int((avg_rating/5)*100) if avg_rating else 0

    trend = []
    window = deque(maxlen=7)
    for d in sorted(daily):
        avg = round(sum(daily[d])/len(daily[d]), 2)
        window.append(avg)
        trend.append({"week": d, "avg": round(sum(window)/len(window), 2)})

    month_trend = [
        {"month": m, "avg_sentiment": round(sum(v)/len(v), 3)}
        for m, v in sorted(monthly.items())
    ]

    return {
        "total_reviews": total,
        "average_rating": avg_rating,
        "reputation_score": reputation_score,
        "ratings": rating_dist,
        "emotions": emotions,
        "sentiment_trend": trend,
        "monthly_sentiment": month_trend,
        "response_rate": round((responded/total)*100, 2),
        "complaint_ratio": round((complaints/total)*100, 2),
        "sentiment_balance": round(sum(sentiments)/len(sentiments), 3) if sentiments else 0
    }

# -------------------------------------------------------------------
# MAIN DASHBOARD (UNCHANGED OUTPUT)
# -------------------------------------------------------------------
@router.get("/ai/insights")
async def analyze_business(
    company_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except Exception:
        return _empty_dashboard()

    stmt = select(Review).where(
        and_(
            Review.company_id == company_id,
            or_(
                Review.google_review_time.is_(None),
                and_(Review.google_review_time >= start_dt,
                     Review.google_review_time <= end_dt)
            )
        )
    )
    res = await session.execute(stmt)
    reviews = res.scalars().all()

    analytics = compute_analytics(reviews)
    if not analytics:
        return _empty_dashboard()

    return {
        "metadata": {"total_reviews": analytics["total_reviews"]},
        "kpis": {
            "average_rating": analytics["average_rating"],
            "reputation_score": analytics["reputation_score"],
        },
        "visualizations": {
            "ratings": analytics["ratings"],
            "emotions": analytics["emotions"],
            "sentiment_trend": analytics["sentiment_trend"],
        }
    }

# -------------------------------------------------------------------
# CHATBOT EXPLANATION WITH MEMORY
# -------------------------------------------------------------------
@router.get("/chatbot/explain/{company_id}")
async def chatbot(company_id: int, question: str, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_analytics(res.scalars().all())

    if not analytics:
        return {"answer": "No review data available yet."}

    q = question.lower()
    if "why" in q and "month" in q:
        answer = "Sentiment changed due to variation in review tone and volume between recent months."
    elif "forecast" in q:
        answer = "Based on recent sentiment patterns, the next few months should remain stable if no major issues arise."
    else:
        answer = (
            f"Your average rating is {analytics['average_rating']} "
            f"and overall sentiment is {max(analytics['emotions'], key=analytics['emotions'].get)}."
        )

    remember(company_id, "user", question)
    remember(company_id, "ai", answer)

    return {"answer": answer, "memory": recall(company_id)}

# -------------------------------------------------------------------
# WHY THIS MONTH CHANGED
# -------------------------------------------------------------------
@router.get("/why-month-changed/{company_id}")
async def why_changed(company_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_analytics(res.scalars().all())

    m = analytics["monthly_sentiment"] if analytics else []
    if len(m) < 2:
        return {"explanation": "Not enough data for month‑to‑month comparison."}

    last = m[-1]
    prev = m[-2]
    direction = "improved" if last["avg_sentiment"] > prev["avg_sentiment"] else "declined"

    return {
        "explanation": f"Sentiment {direction} from {prev['month']} to {last['month']} due to changes in review sentiment intensity."
    }

# -------------------------------------------------------------------
# 3‑MONTH FORECAST
# -------------------------------------------------------------------
@router.get("/forecast/{company_id}")
async def forecast(company_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_analytics(res.scalars().all())

    if not analytics:
        return {"forecast": "Not enough data for forecast."}

    base = analytics["average_rating"]
    return {
        "forecast": [
            {"month": "Next Month", "expected_rating": round(base - 0.05, 2)},
            {"month": "Month +2", "expected_rating": round(base - 0.10, 2)},
            {"month": "Month +3", "expected_rating": round(base - 0.15, 2)},
        ]
    }

# -------------------------------------------------------------------
# EXECUTIVE PDF REPORT
# -------------------------------------------------------------------
@router.get("/executive-report/pdf/{company_id}")
async def executive_pdf(company_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_analytics(res.scalars().all())

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont("Helvetica", 12)

    pdf.drawString(50, 750, "Executive Review Intelligence Report")
    pdf.drawString(50, 720, f"Company ID: {company_id}")

    if analytics:
        pdf.drawString(50, 690, f"Average Rating: {analytics['average_rating']}")
        pdf.drawString(50, 660, f"Reputation Score: {analytics['reputation_score']}")
        pdf.drawString(50, 630, f"Response Rate: {analytics['response_rate']}%")

    pdf.drawString(50, 600, "Recommendation: Address negative feedback promptly.")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=executive_report.pdf"},
    )

# -------------------------------------------------------------------
# COMPETITOR INTELLIGENCE
# -------------------------------------------------------------------
@router.get("/competitors/{company_id}")
async def competitors(company_id: int, session: AsyncSession = Depends(get_session)):
    main_res = await session.execute(select(Review).where(Review.company_id == company_id))
    main = compute_analytics(main_res.scalars().all())

    comp_res = await session.execute(select(Competitor).where(Competitor.company_id == company_id))
    competitors = comp_res.scalars().all()

    insights = []
    if main:
        for c in competitors:
            if getattr(c, "rating", None) and c.rating > main["average_rating"]:
                insights.append(f"{c.name} outperforms your rating with {c.rating}")

    return {
        "company_rating": main["average_rating"] if main else 0,
        "competitor_insights": insights
    }

# -------------------------------------------------------------------
# REVENUE RISK (UNCHANGED)
# -------------------------------------------------------------------
@router.get("/revenue")
async def revenue(company_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(func.avg(Review.rating)).where(Review.company_id == company_id))
    avg = res.scalar() or 0

    if avg >= 4:
        return {"risk_percent": 10, "impact": "Low"}
    elif avg >= 3:
        return {"risk_percent": 40, "impact": "Medium"}
    return {"risk_percent": 80, "impact": "High"}

def _empty_dashboard():
    return JSONResponse({
        "metadata": {"total_reviews": 0},
        "kpis": {"average_rating": 0, "reputation_score": 0},
        "visualizations": {
            "ratings": {1:0,2:0,3:0,4:0,5:0},
            "emotions": {"Positive":0,"Neutral":0,"Negative":0},
            "sentiment_trend": []
        }
    })
