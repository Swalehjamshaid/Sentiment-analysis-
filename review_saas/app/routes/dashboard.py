from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from collections import defaultdict, Counter
from io import BytesIO

from reportlab.pdfgen import canvas

from app.core.db import get_session
from app.core.models import Review

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# =========================================================
# Helpers
# =========================================================

def safe_avg(values):
    return round(sum(values) / len(values), 2) if values else 0

def month_label(dt):
    return dt.strftime("%b %Y")

# =========================================================
# MAIN DASHBOARD DATA (Analyze Business)
# =========================================================
@router.get("/ai/insights")
async def analyze_business(
    company_id: int = Query(...),

    # Frontend sends broken query params (&amp;start / &amp;end)
    start: str | None = Query(None),
    end: str | None = Query(None),
    amp_start: str | None = Query(None, alias="amp;start"),
    amp_end: str | None = Query(None, alias="amp;end"),

    session: AsyncSession = Depends(get_session),
):
    start_val = start or amp_start
    end_val = end or amp_end

    try:
        start_dt = datetime.fromisoformat(start_val) if start_val else None
        end_dt = datetime.fromisoformat(end_val) if end_val else None
    except Exception:
        start_dt = None
        end_dt = None

    query = select(Review).where(Review.company_id == company_id)

    if start_dt and end_dt:
        query = query.where(
            Review.google_review_time >= start_dt,
            Review.google_review_time <= end_dt,
        )

    result = await session.execute(query)
    reviews = result.scalars().all()

    if not reviews:
        return _empty_dashboard()

    # ===============================
    # KPIs
    # ===============================
    ratings_list = [r.rating for r in reviews if isinstance(r.rating, (int, float))]
    avg_rating = safe_avg(ratings_list)
    reputation_score = int((avg_rating / 5) * 100) if avg_rating else 0

    # ===============================
    # Distributions
    # ===============================
    ratings = {i: 0 for i in range(1, 6)}
    emotions = {"Positive": 0, "Neutral": 0, "Negative": 0}
    monthly_trend = defaultdict(list)
    words = []

    for r in reviews:
        if r.rating in ratings:
            ratings[r.rating] += 1

        score = r.sentiment_score or 0
        if score >= 0.25:
            emotions["Positive"] += 1
        elif score <= -0.25:
            emotions["Negative"] += 1
        else:
            emotions["Neutral"] += 1

        if r.google_review_time:
            month = month_label(r.google_review_time)
            monthly_trend[month].append(r.rating or 0)

        if r.text:
            words.extend(r.text.lower().split())

    sentiment_trend = [
        {"week": m, "avg": safe_avg(v)}
        for m, v in sorted(monthly_trend.items())
    ]

    keywords = [
        {"text": w, "value": c}
        for w, c in Counter(words).most_common(15)
    ]

    # ✅ EXACT STRUCTURE EXPECTED BY FRONTEND
    return {
        "metadata": {
            "total_reviews": len(reviews)
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": reputation_score
        },
        "visualizations": {
            "ratings": ratings,
            "emotions": emotions,
            "sentiment_trend": sentiment_trend,
            "keywords": keywords
        }
    }

# =========================================================
# CHATBOT (Strategy Consultant)
# =========================================================
@router.get("/chatbot/explain/{company_id}")
async def chatbot_explain(
    company_id: int,
    question: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(func.avg(Review.rating)).where(Review.company_id == company_id)
    )
    avg_rating = result.scalar() or 0

    q = question.lower()
    if "why" in q or "decline" in q:
        answer = "Recent changes are caused by month-to-month sentiment shifts and rating variability."
    elif "grow" in q or "improve" in q:
        answer = "Growth improves when negative feedback is addressed quickly and positive experiences are reinforced."
    else:
        answer = f"The current average rating is {round(avg_rating, 2)}. Overall performance remains stable."

    return {"answer": answer}

# =========================================================
# REVENUE RISK
# =========================================================
@router.get("/revenue")
async def revenue_risk(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(func.avg(Review.rating)).where(Review.company_id == company_id)
    )
    avg_rating = result.scalar() or 0

    if avg_rating >= 4:
        return {"risk_percent": 10, "impact": "Low"}
    elif avg_rating >= 3:
        return {"risk_percent": 40, "impact": "Medium"}
    return {"risk_percent": 80, "impact": "High"}

# =========================================================
# EXECUTIVE PDF REPORT
# =========================================================
@router.get("/executive-report/pdf/{company_id}")
async def executive_report_pdf(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .where(Review.company_id == company_id)
    )
    avg_rating, count = result.first()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont("Helvetica", 12)

    pdf.drawString(50, 750, "Executive Review Intelligence Report")
    pdf.drawString(50, 720, f"Company ID: {company_id}")
    pdf.drawString(50, 690, f"Average Rating: {round(avg_rating or 0, 2)}")
    pdf.drawString(50, 660, f"Total Reviews: {count or 0}")
    pdf.drawString(50, 630, "Recommendation: Maintain service quality and respond to customer feedback.")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=dashboard_report.pdf"}
    )

# =========================================================
# SAFE EMPTY RESPONSE
# =========================================================
def _empty_dashboard():
    return JSONResponse({
        "metadata": {"total_reviews": 0},
        "kpis": {
            "average_rating": 0,
            "reputation_score": 0
        },
        "visualizations": {
            "ratings": {i: 0 for i in range(1, 6)},
            "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "sentiment_trend": [],
            "keywords": []
        }
    })
