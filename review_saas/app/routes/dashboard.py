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


# ==========================================================
# Helpers
# ==========================================================

def month_label(dt: datetime) -> str:
    return dt.strftime("%b %Y")


def safe_avg(values):
    return round(sum(values) / len(values), 2) if values else 0


# ==========================================================
# MAIN DASHBOARD ENDPOINT (100% MATCHES FRONTEND)
# ==========================================================
@router.get("/ai/insights")
async def analyze_business(
    company_id: int = Query(...),

    # ✅ accept both normal and "&amp;"-polluted params
    start: str | None = Query(None),
    end: str | None = Query(None),

    amp_start: str | None = Query(None, alias="amp;start"),
    amp_end: str | None = Query(None, alias="amp;end"),

    session: AsyncSession = Depends(get_session),
):
    # Resolve broken front-end params
    start_val = start or amp_start
    end_val = end or amp_end

    try:
        start_dt = datetime.fromisoformat(start_val) if start_val else datetime(2000, 1, 1)
        end_dt = datetime.fromisoformat(end_val) if end_val else datetime.utcnow()
    except Exception:
        start_dt = datetime(2000, 1, 1)
        end_dt = datetime.utcnow()

    result = await session.execute(
        select(Review).where(
            Review.company_id == company_id,
            Review.google_review_time >= start_dt,
            Review.google_review_time <= end_dt
        )
    )
    reviews = result.scalars().all()

    if not reviews:
        return _empty_dashboard()

    # KPIs
    ratings_list = [r.rating for r in reviews if isinstance(r.rating, (int, float))]
    avg_rating = safe_avg(ratings_list)
    reputation_score = int((avg_rating / 5) * 100) if avg_rating else 0

    # Rating distribution
    ratings_dist = {i: 0 for i in range(1, 6)}

    # Sentiment
    emotions = {"Positive": 0, "Neutral": 0, "Negative": 0}

    # Month-wise trend
    monthly_map = defaultdict(list)

    # Keywords
    words = []

    for r in reviews:
        if r.rating in ratings_dist:
            ratings_dist[r.rating] += 1

        score = r.sentiment_score or 0
        if score >= 0.25:
            emotions["Positive"] += 1
        elif score <= -0.25:
            emotions["Negative"] += 1
        else:
            emotions["Neutral"] += 1

        if r.google_review_time:
            month = month_label(r.google_review_time)
            monthly_map[month].append(r.rating or 0)

        if r.text:
            words.extend(r.text.lower().split())

    sentiment_trend = [
        {"week": m, "avg": safe_avg(v)}
        for m, v in sorted(monthly_map.items())
    ]

    keywords = [
        {"text": w, "value": c}
        for w, c in Counter(words).most_common(15)
    ]

    return {
        "metadata": {"total_reviews": len(reviews)},
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": reputation_score
        },
        "visualizations": {
            "ratings": ratings_dist,
            "emotions": emotions,
            "sentiment_trend": sentiment_trend,
            "keywords": keywords
        }
    }


# ==========================================================
# CHATBOT (Frontend expects this EXACT path)
# ==========================================================
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

    # Always return something (frontend requirement)
    answer = (
        f"Based on recent reviews, the average rating is {round(avg_rating, 2)}. "
        "Customer sentiment suggests focusing on service consistency and response quality."
    )

    if "why" in question.lower():
        answer = (
            "Recent changes are driven by shifts in monthly review sentiment "
            "and rating distribution."
        )

    return {"answer": answer}


# ==========================================================
# REVENUE RISK (Used by UI)
# ==========================================================
@router.get("/revenue")
async def revenue(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    res = await session.execute(
        select(func.avg(Review.rating)).where(Review.company_id == company_id)
    )
    avg = res.scalar() or 0

    if avg >= 4:
        return {"risk_percent": 10, "impact": "Low"}
    elif avg >= 3:
        return {"risk_percent": 40, "impact": "Medium"}
    return {"risk_percent": 80, "impact": "High"}


# ==========================================================
# EXECUTIVE PDF REPORT (Download button)
# ==========================================================
@router.get("/executive-report/pdf/{company_id}")
async def executive_report_pdf(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    res = await session.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .where(Review.company_id == company_id)
    )
    avg_rating, count = res.first()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont("Helvetica", 12)

    pdf.drawString(50, 750, "Executive Review Intelligence Report")
    pdf.drawString(50, 720, f"Company ID: {company_id}")
    pdf.drawString(50, 690, f"Average Rating: {round(avg_rating or 0, 2)}")
    pdf.drawString(50, 660, f"Total Reviews: {count or 0}")
    pdf.drawString(50, 630, "Recommendation: Maintain service quality and respond to feedback.")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=review_report.pdf"}
    )


def _empty_dashboard():
    return JSONResponse({
        "metadata": {"total_reviews": 0},
        "kpis": {"average_rating": 0, "reputation_score": 0},
        "visualizations": {
            "ratings": {i: 0 for i in range(1, 6)},
            "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "sentiment_trend": [],
            "keywords": []
        }
    })
