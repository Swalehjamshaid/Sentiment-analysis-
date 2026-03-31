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
# HELPERS
# =========================================================
def safe_avg(values):
    return round(sum(values) / len(values), 2) if values else 0


def safe_date(val):
    try:
        return datetime.fromisoformat(val) if val else None
    except:
        return None


def month_label(dt):
    return dt.strftime("%b %Y") if dt else "Unknown"


# =========================================================
# MAIN ANALYTICS ENDPOINT
# =========================================================
@router.get("/ai/insights")
async def analyze_business(
    company_id: int = Query(...),

    # Fix for broken frontend params
    start: str | None = Query(None),
    end: str | None = Query(None),
    amp_start: str | None = Query(None, alias="amp;start"),
    amp_end: str | None = Query(None, alias="amp;end"),

    session: AsyncSession = Depends(get_session),
):
    # Resolve date safely
    start_val = start or amp_start
    end_val = end or amp_end

    start_dt = safe_date(start_val)
    end_dt = safe_date(end_val)

    # Base query
    query = select(Review).where(Review.company_id == company_id)

    if start_dt and end_dt:
        query = query.where(
            Review.google_review_time >= start_dt,
            Review.google_review_time <= end_dt
        )

    result = await session.execute(query)
    reviews = result.scalars().all()

    # -----------------------------------------------------
    # EMPTY SAFE RESPONSE
    # -----------------------------------------------------
    if not reviews:
        return _empty_dashboard()

    # -----------------------------------------------------
    # KPI CALCULATIONS
    # -----------------------------------------------------
    ratings_list = [r.rating for r in reviews if isinstance(r.rating, (int, float))]
    avg_rating = safe_avg(ratings_list)
    reputation_score = int((avg_rating / 5) * 100) if avg_rating else 0

    # -----------------------------------------------------
    # VISUAL STRUCTURES (STRICT FORMAT FOR FRONTEND)
    # -----------------------------------------------------
    ratings = {i: 0 for i in range(1, 6)}
    emotions = {"Positive": 0, "Neutral": 0, "Negative": 0}
    monthly = defaultdict(list)
    words = []

    # -----------------------------------------------------
    # LOOP
    # -----------------------------------------------------
    for r in reviews:
        # Ratings
        if r.rating in ratings:
            ratings[r.rating] += 1

        # Sentiment
        score = getattr(r, "sentiment_score", 0) or 0
        if score >= 0.25:
            emotions["Positive"] += 1
        elif score <= -0.25:
            emotions["Negative"] += 1
        else:
            emotions["Neutral"] += 1

        # Time trend
        if r.google_review_time:
            m = month_label(r.google_review_time)
            monthly[m].append(r.rating or 0)

        # Keywords (SAFE FIELD HANDLING)
        text = getattr(r, "text", None) or getattr(r, "review_text", None)
        if text:
            words.extend(text.lower().split())

    # -----------------------------------------------------
    # TREND FIX (SORTED)
    # -----------------------------------------------------
    sentiment_trend = []
    for m in sorted(monthly.keys()):
        sentiment_trend.append({
            "week": m,
            "avg": safe_avg(monthly[m])
        })

    # -----------------------------------------------------
    # KEYWORDS (FRONTEND SAFE)
    # -----------------------------------------------------
    keywords = [
        {"text": w, "value": c}
        for w, c in Counter(words).most_common(20)
    ]

    # -----------------------------------------------------
    # FINAL RESPONSE (STRICT CONTRACT)
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
            "keywords": keywords  # 🔥 REQUIRED FOR UI
        }
    }


# =========================================================
# CHATBOT (STABLE)
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

    if "why" in q:
        answer = "Changes are driven by shifts in customer sentiment and recent review trends."
    elif "improve" in q or "grow" in q:
        answer = "Focus on responding to negative reviews and improving customer experience."
    elif "trend" in q:
        answer = "Recent trends show fluctuations in ratings influenced by review volume."
    else:
        answer = f"Your current average rating is {round(avg_rating, 2)}."

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
# PDF REPORT
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
    pdf.drawString(50, 630, "Recommendation: Improve customer satisfaction & respond faster.")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=dashboard_report.pdf"}
    )


# =========================================================
# SAFE EMPTY RESPONSE (NO FRONTEND CRASH)
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
