# filename: app/routes/dashboard.py

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

# IMPORTANT:
# main.py mounts this router under /dashboard (no /api here)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def safe_avg(values):
    return round(sum(values) / len(values), 2) if values else 0.0


def month_label(dt: datetime) -> str:
    return dt.strftime("%b %Y")  # ex: "Mar 2026"


# ---------------------------------------------------------
# MAIN DASHBOARD ENDPOINT
# Frontend calls:
#   GET /dashboard/ai/insights?company_id=...&amp;start=...&amp;end=...
# ---------------------------------------------------------
@router.get("/ai/insights")
async def ai_insights(
    company_id: int = Query(...),

    # Frontend sends &amp;start / &amp;end due to HTML encoding
    start: str | None = Query(None),
    end: str | None = Query(None),
    amp_start: str | None = Query(None, alias="amp;start"),
    amp_end: str | None = Query(None, alias="amp;end"),

    session: AsyncSession = Depends(get_session),
):
    # Resolve broken params safely
    start_val = start or amp_start
    end_val = end or amp_end

    try:
        start_dt = datetime.fromisoformat(start_val) if start_val else None
        end_dt = datetime.fromisoformat(end_val) if end_val else None
    except Exception:
        start_dt = None
        end_dt = None

    # Base query (PostgreSQL / asyncpg)
    stmt = select(Review).where(Review.company_id == company_id)

    # Apply date filter only if valid
    if start_dt and end_dt:
        stmt = stmt.where(
            Review.google_review_time >= start_dt,
            Review.google_review_time <= end_dt,
        )

    result = await session.execute(stmt)
    reviews = result.scalars().all()

    if not reviews:
        return _empty_dashboard()

    # -----------------------------------------------------
    # KPI CALCULATIONS
    # -----------------------------------------------------
    ratings_list = [r.rating for r in reviews if isinstance(r.rating, (int, float))]
    avg_rating = safe_avg(ratings_list)
    reputation_score = avg_rating  # frontend expects to show this directly

    # -----------------------------------------------------
    # Rating Distribution (BAR CHART)
    # -----------------------------------------------------
    ratings = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    # -----------------------------------------------------
    # Emotion Radar (RADAR CHART)
    # Keys must match frontend expectations
    # -----------------------------------------------------
    emotions = {
        "Positive": 0,
        "Neutral": 0,
        "Negative": 0,
    }

    # -----------------------------------------------------
    # Sentiment Trend (LINE CHART, month-wise)
    # Each item must have { week, avg }
    # -----------------------------------------------------
    trend_map = defaultdict(list)

    # -----------------------------------------------------
    # Keyword Extraction
    # -----------------------------------------------------
    words = []

    for r in reviews:
        # Rating distribution
        if r.rating in ratings:
            ratings[r.rating] += 1

        # Sentiment buckets
        score = r.sentiment_score or 0.0
        if score >= 0.25:
            emotions["Positive"] += 1
        elif score <= -0.25:
            emotions["Negative"] += 1
        else:
            emotions["Neutral"] += 1

        # Month-wise aggregation
        if r.google_review_time:
            key = month_label(r.google_review_time)
            trend_map[key].append(r.rating or 0)

        # Keywords
        if r.text:
            words.extend(r.text.lower().split())

    sentiment_trend = [
        {"week": month, "avg": safe_avg(vals)}
        for month, vals in sorted(trend_map.items())
    ]

    keywords = [
        {"text": w, "value": c}
        for w, c in Counter(words).most_common(15)
    ]

    # -----------------------------------------------------
    # FINAL RESPONSE (EXACT SHAPE FRONTEND USES)
    # -----------------------------------------------------
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


# ---------------------------------------------------------
# REVENUE RISK ENDPOINT
# Frontend calls: GET /dashboard/revenue?company_id=...
# ---------------------------------------------------------
@router.get("/revenue")
async def revenue_risk(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(func.avg(Review.rating)).where(Review.company_id == company_id)
    )
    avg_rating = result.scalar() or 0.0

    if avg_rating >= 4:
        return {"risk_percent": 10, "impact": "Low"}
    elif avg_rating >= 3:
        return {"risk_percent": 40, "impact": "Medium"}
    else:
        return {"risk_percent": 80, "impact": "High"}


# ---------------------------------------------------------
# CHATBOT ENDPOINT
# Frontend calls:
#   GET /dashboard/chatbot/explain/{company_id}?question=...
# ---------------------------------------------------------
@router.get("/chatbot/explain/{company_id}")
async def chatbot_explain(
    company_id: int,
    question: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(func.avg(Review.rating)).where(Review.company_id == company_id)
    )
    avg_rating = result.scalar() or 0.0

    q = question.lower()

    if "why" in q:
        answer = (
            "Rating changes are driven by month‑to‑month sentiment shifts "
            "and variations in customer feedback volume."
        )
    elif "grow" in q or "improve" in q:
        answer = (
            "Focus on addressing negative reviews quickly and reinforcing "
            "positive experiences to improve growth."
        )
    else:
        answer = f"The current average rating is {round(avg_rating, 2)}."

    return {"answer": answer}


# ---------------------------------------------------------
# EXECUTIVE PDF REPORT
# Frontend calls:
#   GET /dashboard/executive-report/pdf/{company_id}
# ---------------------------------------------------------
@router.get("/executive-report/pdf/{company_id}")
async def executive_report_pdf(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .where(Review.company_id == company_id)
    )
    avg_rating, total = result.first()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont("Helvetica", 12)

    pdf.drawString(50, 750, "Executive Review Intelligence Report")
    pdf.drawString(50, 720, f"Company ID: {company_id}")
    pdf.drawString(50, 690, f"Average Rating: {round(avg_rating or 0, 2)}")
    pdf.drawString(50, 660, f"Total Reviews: {total or 0}")
    pdf.drawString(
        50,
        630,
        "Recommendation: Monitor customer sentiment and address issues promptly."
    )

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=dashboard_report.pdf"}
    )


# ---------------------------------------------------------
# EMPTY FALLBACK (NEVER BREAKS UI)
# ---------------------------------------------------------
def _empty_dashboard():
    return JSONResponse({
        "metadata": {"total_reviews": 0},
        "kpis": {
            "average_rating": 0,
            "reputation_score": 0
        },
        "visualizations": {
            "ratings": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "sentiment_trend": [],
            "keywords": []
        }
    })
