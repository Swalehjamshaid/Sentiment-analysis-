from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from collections import defaultdict
from datetime import datetime
import random

from app.db.session import get_db
from app.models.review import Review
from app.models.company import Company

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# ================================
# ✅ AI INSIGHTS (MAIN ANALYZE API)
# ================================
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

        # ======================
        # KPI CALCULATIONS
        # ======================
        avg_rating = round(
            sum(r.rating for r in reviews) / total_reviews, 2
        ) if total_reviews > 0 else 0

        reputation_score = int(avg_rating * 20)  # scale 0–100

        # ======================
        # RATINGS DISTRIBUTION
        # ======================
        ratings = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in reviews:
            if r.rating in ratings:
                ratings[r.rating] += 1

        # ======================
        # SENTIMENT TREND
        # ======================
        trend = defaultdict(list)

        for r in reviews:
            key = r.created_at.strftime("%Y-%m-%d")
            trend[key].append(r.rating)

        sentiment_trend = []
        for k, v in trend.items():
            sentiment_trend.append({
                "date": k,
                "avg": round(sum(v)/len(v), 2)
            })

        sentiment_trend = sorted(sentiment_trend, key=lambda x: x["date"])

        # ======================
        # EMOTIONS (MOCK AI)
        # ======================
        emotions = {
            "happy": random.randint(20, 80),
            "angry": random.randint(5, 40),
            "neutral": random.randint(10, 60),
            "sad": random.randint(5, 30),
            "surprised": random.randint(5, 25)
        }

        # ======================
        # FINAL RESPONSE
        # ======================
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


# ================================
# ✅ REVENUE RISK API
# ================================
@router.get("/revenue")
def revenue_risk(company_id: int, db: Session = Depends(get_db)):
    reviews = db.query(Review).filter(Review.company_id == company_id).all()

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


# ================================
# ✅ AI CHAT
# ================================
@router.post("/chat")
def chat_ai(company_id: int, message: str, db: Session = Depends(get_db)):
    reviews = db.query(Review).filter(Review.company_id == company_id).all()

    avg = round(sum(r.rating for r in reviews)/len(reviews), 2) if reviews else 0

    return {
        "answer": f"Based on your rating ({avg}), focus on improving customer service and response time."
    }
