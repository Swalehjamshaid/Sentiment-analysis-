from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from collections import defaultdict
from datetime import datetime
import random

# ✅ FIXED IMPORT (IMPORTANT)
from app.database import get_db

from app.models.review import Review
from app.models.company import Company

# ✅ PREFIX MUST MATCH FRONTEND CALLS
router = APIRouter(prefix="/api", tags=["Dashboard"])


# =====================================================
# 🔥 AI INSIGHTS (MAIN ANALYZE BUTTON)
# URL: /api/ai/insights
# =====================================================
@router.get("/ai/insights")
def get_ai_insights(
    company_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    db: Session = Depends(get_db)
):
    try:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)

        reviews = db.query(Review).filter(
            Review.company_id == company_id,
            Review.created_at >= start_date,
            Review.created_at <= end_date
        ).all()

        total_reviews = len(reviews)

        # ================= KPIs =================
        avg_rating = round(
            sum(r.rating for r in reviews) / total_reviews, 2
        ) if total_reviews > 0 else 0

        reputation_score = int(avg_rating * 20)  # scale 0–100

        # ================= RATINGS =================
        ratings = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in reviews:
            if r.rating in ratings:
                ratings[r.rating] += 1

        # ================= TREND =================
        trend = defaultdict(list)
        for r in reviews:
            key = r.created_at.strftime("%Y-%m-%d")
            trend[key].append(r.rating)

        sentiment_trend = [
            {"date": k, "avg": round(sum(v) / len(v), 2)}
            for k, v in trend.items()
        ]

        sentiment_trend.sort(key=lambda x: x["date"])

        # ================= EMOTIONS (AI MOCK) =================
        emotions = {
            "Happy": random.randint(20, 80),
            "Angry": random.randint(5, 40),
            "Neutral": random.randint(10, 60),
            "Sad": random.randint(5, 30),
            "Surprised": random.randint(5, 25)
        }

        # ================= RESPONSE =================
        return {
            "metadata": {
                "total_reviews": total_reviews
            },
            "kpis": {
                "benchmark": {
                    "your_avg": avg_rating
                },
                "reputation_score": reputation_score
            },
            "visualizations": {
                "emotions": emotions,
                "sentiment_trend": sentiment_trend,
                "ratings": ratings
            }
        }

    except Exception as e:
        return {"error": str(e)}


# =====================================================
# 🔥 REVENUE RISK
# URL: /api/dashboard/revenue
# =====================================================
@router.get("/dashboard/revenue")
def revenue_risk(company_id: int, db: Session = Depends(get_db)):
    reviews = db.query(Review).filter(
        Review.company_id == company_id
    ).all()

    total = len(reviews)
    low_reviews = len([r for r in reviews if r.rating <= 2])

    risk_percent = int((low_reviews / total) * 100) if total else 0

    if risk_percent > 50:
        impact = "HIGH"
    elif risk_percent > 25:
        impact = "MEDIUM"
    else:
        impact = "LOW"

    return {
        "risk_percent": risk_percent,
        "impact": impact
    }


# =====================================================
# 🔥 AI CHAT
# URL: /api/dashboard/chat
# =====================================================
@router.post("/dashboard/chat")
def chat_ai(
    company_id: int,
    message: str = Body(...),
    db: Session = Depends(get_db)
):
    reviews = db.query(Review).filter(
        Review.company_id == company_id
    ).all()

    avg = round(
        sum(r.rating for r in reviews) / len(reviews), 2
    ) if reviews else 0

    return {
        "answer": f"Based on your current rating ({avg}), improve service speed, staff behavior, and complaint resolution."
    }
