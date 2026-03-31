from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from datetime import datetime
from collections import defaultdict, deque

from app.core.db import get_session
from app.core.models import Review, Competitor

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ==========================================================
# SHARED ANALYTICS (INTERNAL, FLEXIBLE)
# ==========================================================

def compute_core_analytics(reviews):
    total = len(reviews)
    if total == 0:
        return None

    ratings = []
    sentiments = []
    rating_dist = {1:0,2:0,3:0,4:0,5:0}
    emotions = {"Positive":0,"Neutral":0,"Negative":0}
    daily = defaultdict(list)

    responded = 0
    complaints = 0
    praise = 0

    for r in reviews:
        if isinstance(r.rating, (int, float)):
            ratings.append(r.rating)
        if isinstance(r.sentiment_score, (int, float)):
            sentiments.append(r.sentiment_score)

        if r.rating in rating_dist:
            rating_dist[r.rating] += 1

        s = r.sentiment_score or 0.0
        if s >= 0.25:
            emotions["Positive"] += 1
        elif s <= -0.25:
            emotions["Negative"] += 1
        else:
            emotions["Neutral"] += 1

        if r.google_review_time:
            day = r.google_review_time.strftime("%Y-%m-%d")
            daily[day].append(r.rating or 0)

        if getattr(r, "review_reply_text", None):
            responded += 1
        if getattr(r, "is_complaint", False):
            complaints += 1
        if getattr(r, "is_praise", False):
            praise += 1

    avg_rating = round(sum(ratings)/len(ratings), 2) if ratings else 0
    reputation_score = int((avg_rating/5)*100) if avg_rating else 0

    # 7‑day rolling trend (used by dashboard)
    trend = []
    window = deque(maxlen=7)
    for d in sorted(daily):
        avg = round(sum(daily[d])/len(daily[d]), 2)
        window.append(avg)
        trend.append({"week": d, "avg": round(sum(window)/len(window), 2)})

    return {
        "total_reviews": total,
        "average_rating": avg_rating,
        "reputation_score": reputation_score,
        "ratings": rating_dist,
        "emotions": emotions,
        "sentiment_trend": trend,
        # hidden extras for alerts/chatbot/exec
        "response_rate": round((responded/total)*100, 2),
        "complaint_ratio": round((complaints/total)*100, 2),
        "praise_ratio": round((praise/total)*100, 2),
        "sentiment_balance": round(sum(sentiments)/len(sentiments), 3) if sentiments else 0,
        "daily_map": daily,
    }


def month_wise_trend(reviews):
    """Aggregates ratings month‑by‑month (YYYY‑MM)."""
    month_map = defaultdict(list)
    for r in reviews:
        if r.google_review_time:
            m = r.google_review_time.strftime("%Y-%m")
            month_map[m].append(r.rating or 0)

    return [
        {"month": m, "avg": round(sum(v)/len(v), 2)}
        for m, v in sorted(month_map.items())
        if v
    ]


def generate_alerts(analytics):
    alerts = []
    if analytics["average_rating"] < 3.8:
        alerts.append("Average rating approaching risk threshold.")
    if analytics["complaint_ratio"] > 25:
        alerts.append("High complaint ratio detected.")
    # declining slope check
    t = analytics["sentiment_trend"]
    if len(t) >= 6 and t[-1]["avg"] < t[-6]["avg"]:
        alerts.append("Sentiment trend is declining.")
    return alerts


def forecast_simple(analytics, horizon_days=30):
    """Very light, safe forecast based on recent slope (no ML, no UI breakage)."""
    t = analytics["sentiment_trend"]
    if len(t) < 5:
        return {"forecast": "Insufficient data for forecast."}

    delta = t[-1]["avg"] - t[-5]["avg"]
    direction = "downward" if delta < 0 else "stable"
    return {
        "forecast": f"Short‑term sentiment is likely {direction} over the next {horizon_days} days."
    }


def executive_summary_text(analytics):
    return (
        f"Executive Summary: The business has an average rating of "
        f"{analytics['average_rating']} with a reputation score of "
        f"{analytics['reputation_score']}/100. Customer sentiment is predominantly "
        f"{max(analytics['emotions'], key=analytics['emotions'].get)}. "
        f"Response rate is {analytics['response_rate']}%. "
        f"Priority actions include addressing complaints and sustaining response quality."
    )


# ==========================================================
# EXISTING DASHBOARD ENDPOINT (UNCHANGED OUTPUT)
# ==========================================================

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
        return _empty_dashboard_response()

    stmt = select(Review).where(
        and_(
            Review.company_id == company_id,
            or_(
                Review.google_review_time.is_(None),
                and_(Review.google_review_time >= start_dt,
                     Review.google_review_time <= end_dt),
            ),
        )
    )
    result = await session.execute(stmt)
    reviews = result.scalars().all()

    analytics = compute_core_analytics(reviews)
    if not analytics:
        return _empty_dashboard_response()

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
        },
    }


# ==========================================================
# MONTH‑BY‑MONTH CHARTS (NEW, DOES NOT BREAK UI)
# ==========================================================

@router.get("/monthly/{company_id}")
async def month_by_month(company_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    reviews = res.scalars().all()
    return {"monthly_trend": month_wise_trend(reviews)}


# ==========================================================
# CHATBOT EXPLANATIONS (DATA‑DRIVEN)
# ==========================================================

@router.get("/chatbot/explain/{company_id}")
async def chatbot_explain(company_id: int, question: str, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_core_analytics(res.scalars().all())
    if not analytics:
        return {"answer": "No sufficient data to analyze yet."}

    # Simple intent‑aware replies (extremely safe)
    q = question.lower()
    if "why" in q or "drop" in q or "decline" in q:
        reasons = []
        if analytics["complaint_ratio"] > 20:
            reasons.append("an increase in complaints")
        if analytics["response_rate"] < 50:
            reasons.append("low response rate to reviews")
        if not reasons:
            reasons.append("normal variance in customer feedback")
        return {"answer": "Rating changes are likely due to " + ", ".join(reasons) + "."}

    if "risk" in q:
        alerts = generate_alerts(analytics)
        return {"answer": "Current risks: " + (", ".join(alerts) if alerts else "no major risks detected.")}

    return {"answer": executive_summary_text(analytics)}


# ==========================================================
# ALERTS & FORECASTING
# ==========================================================

@router.get("/alerts/{company_id}")
async def alerts_and_forecast(company_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_core_analytics(res.scalars().all())
    if not analytics:
        return {"alerts": [], "forecast": "No data available."}

    return {
        "alerts": generate_alerts(analytics),
        "forecast": forecast_simple(analytics),
    }


# ==========================================================
# EXECUTIVE REPORTING
# ==========================================================

@router.get("/executive-summary/{company_id}")
async def executive_report(company_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_core_analytics(res.scalars().all())
    if not analytics:
        return {"summary": "No data available."}

    return {"summary": executive_summary_text(analytics)}


# ==========================================================
# COMPETITOR INTELLIGENCE
# ==========================================================

@router.get("/competitors/{company_id}")
async def competitor_intelligence(company_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    main = compute_core_analytics(res.scalars().all())

    comp_res = await session.execute(select(Competitor).where(Competitor.company_id == company_id))
    competitors = comp_res.scalars().all()

    insights = []
    if main:
        for c in competitors:
            if getattr(c, "rating", None) and c.rating > main["average_rating"]:
                insights.append(f"{c.name} outperforms with rating {c.rating}")

    return {
        "company_rating": main["average_rating"] if main else 0,
        "competitor_insights": insights,
    }


# ==========================================================
# REVENUE RISK (UNCHANGED)
# ==========================================================

@router.get("/revenue")
async def revenue_risk(company_id: int = Query(...), session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(func.avg(Review.rating)).where(Review.company_id == company_id))
    avg = res.scalar() or 0
    if avg >= 4:
        return {"risk_percent": 10, "impact": "Low"}
    if avg >= 3:
        return {"risk_percent": 40, "impact": "Medium"}
    return {"risk_percent": 80, "impact": "High"}


def _empty_dashboard_response():
    return JSONResponse({
        "metadata": {"total_reviews": 0},
        "kpis": {"average_rating": 0, "reputation_score": 0},
        "visualizations": {
            "ratings": {1:0,2:0,3:0,4:0,5:0},
            "emotions": {"Positive":0,"Neutral":0,"Negative":0},
            "sentiment_trend": [],
        },
    })
