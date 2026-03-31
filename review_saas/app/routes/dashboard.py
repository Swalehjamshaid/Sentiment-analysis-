# ===================================================================
# PROJECT: ReviewSaaS - AI Intelligence Dashboard
# MODULE: app.routes.dashboard
# DESCRIPTION: Final 100% Integrated Backend for dashboard.html
# ===================================================================

from __future__ import annotations
import re
import logging
from io import BytesIO
from collections import defaultdict, deque, Counter
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.core.db import get_session
from app.core.models import Review
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger("ReviewSaaS.Dashboard")

# =========================================================
# HELPERS
# =========================================================
def safe_avg(values: List[float]) -> float:
    """Returns rounded average or 0 if list is empty."""
    return round(sum(values) / len(values), 2) if values else 0.0

def safe_date(val: Optional[str]) -> Optional[datetime]:
    """Parses ISO strings, handling Z and offset formats."""
    if not val: return None
    try:
        return datetime.fromisoformat(val.replace('Z', '+00:00'))
    except:
        return None

def month_label(dt: datetime) -> str:
    """Standardizes time labels for the Trend Chart."""
    return dt.strftime("%b %d") if dt else "Unknown"

# =========================================================
# MAIN ANALYTICS ENDPOINT (INTEGRATED)
# =========================================================
@router.get("/ai/insights")
async def analyze_business(
    company_id: int = Query(...),
    # Handle both clean and URL-encoded "amp;" parameter variants from frontend
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    amp_start: Optional[str] = Query(None, alias="amp;start"),
    amp_end: Optional[str] = Query(None, alias="amp;end"),
    session: AsyncSession = Depends(get_session),
):
    # Resolve the correct date parameters
    start_val = start or amp_start
    end_val = end or amp_end
    
    start_dt = safe_date(start_val)
    end_dt = safe_date(end_val)

    # Database Query
    query = select(Review).where(Review.company_id == company_id)
    if start_dt and end_dt:
        query = query.where(
            and_(
                Review.google_review_time >= start_dt,
                Review.google_review_time <= end_dt
            )
        )

    result = await session.execute(query)
    reviews = result.scalars().all()

    if not reviews:
        return _empty_dashboard()

    # -----------------------------------------------------
    # DATA AGGREGATION
    # -----------------------------------------------------
    ratings_dist = {i: 0 for i in range(1, 6)}
    emotions = {"Positive": 0, "Neutral": 0, "Negative": 0}
    daily_logs = defaultdict(list)
    word_corpus = []
    
    # Process attributes for UI cards and charts
    for r in reviews:
        # 1. Rating Distribution
        rating = r.rating or 0
        if 1 <= rating <= 5:
            ratings_dist[rating] += 1

        # 2. Sentiment/Emotion Radar
        score = getattr(r, "sentiment_score", 0) or 0
        if score >= 0.25: emotions["Positive"] += 1
        elif score <= -0.25: emotions["Negative"] += 1
        else: emotions["Neutral"] += 1

        # 3. Time Series (Grouping by day for smoother trend)
        time_ref = r.google_review_time or r.first_seen_at
        if time_ref:
            label = month_label(time_ref)
            daily_logs[label].append(rating)

        # 4. Keywords
        text = (r.text or "").lower()
        if text:
            # Simple cleaning: only words > 4 chars
            words = re.findall(r'\b[a-z]{5,}\b', text)
            word_corpus.extend(words)

    # -----------------------------------------------------
    # CALCULATE KPIs
    # -----------------------------------------------------
    all_ratings = [r.rating for r in reviews if r.rating]
    avg_rating = safe_avg(all_ratings)
    # Reputation Score (NPS Simulation)
    promoters = len([r for r in all_ratings if r >= 4.5])
    detractors = len([r for r in all_ratings if r <= 3.0])
    total = len(all_ratings)
    reputation_score = int(((promoters - detractors) / total) * 100) if total > 0 else 0

    # -----------------------------------------------------
    # FINAL UI CONTRACT
    # -----------------------------------------------------
    # 5. Trend Chart Data
    sentiment_trend = [
        {"week": label, "avg": safe_avg(ratings)} 
        for label, ratings in daily_logs.items()
    ]

    # 6. Keyword Badges
    stop_words = {'about', 'there', 'their', 'would', 'really', 'place', 'service', 'great', 'business'}
    keywords = [
        {"text": w, "value": c}
        for w, c in Counter(word_corpus).most_common(15)
        if w not in stop_words
    ]

    return {
        "metadata": {
            "total_reviews": len(reviews),
            "generated_at": datetime.now(timezone.utc).isoformat()
        },
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

# =========================================================
# CHATBOT (INTEGRATED)
# =========================================================
@router.get("/chatbot/explain/{company_id}")
async def chatbot_explain(
    company_id: int,
    question: str,
    session: AsyncSession = Depends(get_session),
):
    # Fetch latest average for context
    res = await session.execute(select(func.avg(Review.rating)).where(Review.company_id == company_id))
    avg = res.scalar() or 0
    
    q = question.lower()
    if "why" in q:
        answer = "Fluctuations are common when new reviews shift the moving average or sentiment balance."
    elif "risk" in q or "revenue" in q:
        status = "High" if avg < 3 else "Low"
        answer = f"Your revenue risk is currently {status} because your average rating is {round(avg, 2)}."
    else:
        answer = f"Based on {round(avg, 2)} stars, I suggest prioritizing responses to 1-3 star reviews."

    return {"answer": answer}

# =========================================================
# REVENUE RISK (UI SYNC)
# =========================================================
@router.get("/revenue")
async def revenue_risk(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    res = await session.execute(select(func.avg(Review.rating)).where(Review.company_id == company_id))
    avg = res.scalar() or 0
    
    if avg >= 4.0:
        return {"risk_percent": 10, "impact": "Low"}
    elif avg >= 3.0:
        return {"risk_percent": 45, "impact": "Medium"}
    return {"risk_percent": 85, "impact": "High"}

# =========================================================
# PDF REPORT
# =========================================================
@router.get("/executive-report/pdf/{company_id}")
async def executive_report_pdf(company_id: int, session: AsyncSession = Depends(get_session)):
    stmt = select(func.avg(Review.rating), func.count(Review.id)).where(Review.company_id == company_id)
    res = await session.execute(stmt)
    avg, count = res.first()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    pdf.setTitle(f"Executive Report - {company_id}")
    
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, 750, "Review Intelligence Executive Report")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 720, f"Business ID: {company_id}")
    pdf.drawString(50, 700, f"Analysis Period: Current Data")
    pdf.drawString(50, 680, f"Average Rating: {round(avg or 0, 2)} / 5.0")
    pdf.drawString(50, 660, f"Total Volume: {count or 0} reviews")
    
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Report_{company_id}.pdf"}
    )

# =========================================================
# SAFE EMPTY STATE
# =========================================================
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
