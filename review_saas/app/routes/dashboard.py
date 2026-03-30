from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from collections import Counter
import pandas as pd
import numpy as np

from sklearn.linear_model import LinearRegression
from wordcloud import WordCloud
import base64
from io import BytesIO

# Import your DB + models (adjust if needed)
from app.database import get_db
from app.models import Review

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# -------------------------------
# 🧠 Simple Sentiment Analysis
# -------------------------------
def sentiment_label(rating):
    if rating >= 4:
        return "positive"
    elif rating == 3:
        return "neutral"
    else:
        return "negative"


# -------------------------------
# ☁️ Word Cloud Generator
# -------------------------------
def generate_wordcloud(text_data):
    if not text_data:
        return None

    wc = WordCloud(width=800, height=400, background_color="white")
    wc.generate(" ".join(text_data))

    buffer = BytesIO()
    wc.to_image().save(buffer, format="PNG")

    encoded = base64.b64encode(buffer.getvalue()).decode()
    return encoded


# -------------------------------
# 📊 Main Dashboard Endpoint
# -------------------------------
@router.get("/")
def dashboard_data(db: Session = Depends(get_db)):

    reviews = db.query(Review).all()

    if not reviews:
        return {"message": "No data available"}

    # Convert to DataFrame
    data = pd.DataFrame([{
        "rating": r.rating,
        "review": r.review_text,
        "user": r.reviewer_name,
        "date": r.review_date
    } for r in reviews])

    # -------------------------------
    # 🧠 Sentiment Analysis
    # -------------------------------
    data["sentiment"] = data["rating"].apply(sentiment_label)

    sentiment_counts = data["sentiment"].value_counts().to_dict()

    # -------------------------------
    # ☁️ Word Cloud
    # -------------------------------
    wordcloud_img = generate_wordcloud(data["review"].dropna().tolist())

    # -------------------------------
    # 👥 Reviewer Frequency
    # -------------------------------
    reviewer_counts = Counter(data["user"])
    top_reviewers = dict(reviewer_counts.most_common(5))

    loyal_users = len([u for u, c in reviewer_counts.items() if c > 2])

    # -------------------------------
    # ⭐ NPS Calculation
    # -------------------------------
    promoters = len(data[data["rating"] >= 4])
    detractors = len(data[data["rating"] <= 2])
    total = len(data)

    nps = ((promoters - detractors) / total) * 100

    # -------------------------------
    # 😊 CSAT Score
    # -------------------------------
    csat = (len(data[data["rating"] >= 4]) / total) * 100

    # -------------------------------
    # 📈 Rating Trends
    # -------------------------------
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    trend = data.groupby(data["date"].dt.date)["rating"].mean().reset_index()

    trend_data = trend.to_dict(orient="records")

    # -------------------------------
    # 🤖 Forecasting (Linear Regression)
    # -------------------------------
    trend = trend.dropna()

    forecast = []

    if len(trend) > 2:
        trend["day_index"] = np.arange(len(trend))

        X = trend[["day_index"]]
        y = trend["rating"]

        model = LinearRegression()
        model.fit(X, y)

        future_days = 7
        future_index = np.arange(len(trend), len(trend) + future_days).reshape(-1, 1)

        predictions = model.predict(future_index)

        forecast = predictions.tolist()

    # -------------------------------
    # 📊 Final Response
    # -------------------------------
    return {
        "total_reviews": total,
        "average_rating": round(data["rating"].mean(), 2),

        "sentiment": sentiment_counts,

        "wordcloud": wordcloud_img,

        "top_reviewers": top_reviewers,
        "loyal_customers": loyal_users,

        "nps_score": round(nps, 2),
        "csat_score": round(csat, 2),

        "trend": trend_data,
        "forecast": forecast
    }
