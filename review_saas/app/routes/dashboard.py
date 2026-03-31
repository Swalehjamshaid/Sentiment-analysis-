# app/routes/dashboard.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime
import numpy as np
import pandas as pd

from app.core.db import get_db
from app.models.review import Review
from app.models.company import Company

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# =========================
# Helper Functions
# =========================

def calculate_sentiment(score):
    if score >= 4:
        return "positive"
    elif score == 3:
        return "neutral"
    else:
        return "negative"


def emotion_breakdown(df):
    emotions = {
        "happy": 0,
        "satisfied": 0,
        "neutral": 0,
        "frustrated": 0,
        "angry": 0
    }

    for _, row in df.iterrows():
        rating = row["rating"]
        if rating >= 5:
            emotions["happy"] += 1
        elif rating == 4:
            emotions["satisfied"] += 1
        elif rating == 3:
            emotions["neutral"] += 1
        elif rating == 2:
            emotions["frustrated"] += 1
        else:
            emotions["angry"] += 1

    return emotions


def rating_distribution(df):
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in df["rating"]:
        if r in dist:
            dist[r] += 1
    return dist


def sentiment_trend(df):
    df["date"] = pd.to_datetime(df["created_at"])
    df["week"] = df["date"].dt.to_period("W").astype(str)

    trend = df.groupby("week")["rating"].mean().reset_index()
    trend.rename(columns={"rating": "avg"}, inplace=True)

    return trend.to_dict(orient="records")


# =========================
# MAIN DASHBOARD ENDPOINT
# =========================

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

        if not reviews:
            return {
                "metadata": {"total_reviews": 0},
                "kpis": {},
                "visualizations": {}
            }

        # Convert to DataFrame
        data = [{
            "rating": r.rating,
            "created_at": r.created_at,
            "content": r.content or ""
        } for r in reviews]

        df = pd.DataFrame(data)

        # =========================
        # KPIs
        # =========================
        avg_rating = round(df["rating"].mean(), 2)

        sentiment_score = (
            (df["rating"] >= 4).sum() -
            (df["rating"] <= 2).sum()
        ) / len(df)

        reputation_score = round((sentiment_score + 1) * 50, 2)

        # =========================
        # VISUALS
        # =========================
        visuals = {
            "emotions": emotion_breakdown(df),
            "ratings": rating_distribution(df),
            "sentiment_trend": sentiment_trend(df)
        }

        return {
            "metadata": {
                "total_reviews": len(df)
            },
            "kpis": {
                "average_rating": avg_rating,
                "reputation_score": reputation_score
            },
            "visualizations": visuals
        }

    except Exception as e:
        return {"error": str(e)}


# =========================
# REVENUE RISK API
# =========================

@router.get("/revenue")
def revenue_risk(
    company_id: int,
    db: Session = Depends(get_db)
):
    try:
        reviews = db.query(Review).filter(
            Review.company_id == company_id
        ).all()

        if not reviews:
            return {
                "risk_percent": 0,
                "impact": "LOW"
            }

        ratings = [r.rating for r in reviews]

        negative = sum(1 for r in ratings if r <= 2)
        total = len(ratings)

        risk_percent = round((negative / total) * 100, 2)

        if risk_percent > 40:
            impact = "HIGH"
        elif risk_percent > 20:
            impact = "MEDIUM"
        else:
            impact = "LOW"

        return {
            "risk_percent": risk_percent,
            "impact": impact
        }

    except Exception as e:
        return {"error": str(e)}
