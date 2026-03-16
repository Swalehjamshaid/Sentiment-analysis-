# filename: app/routes/dashboard.py

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date
from typing import Optional, Dict, List

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import Review

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"]
)


# ---------------------------------------------------------
# TEXT ANALYSIS HELPERS
# ---------------------------------------------------------

STOPWORDS = {
    "the","and","is","to","it","a","of","for","in","on","at",
    "this","that","was","with","are","they","very","good"
}

def extract_keywords(texts: List[str], limit: int = 20):

    words = []

    for t in texts:
        tokens = re.findall(r"[a-zA-Z]{4,}", t.lower())

        for token in tokens:
            if token not in STOPWORDS:
                words.append(token)

    counter = Counter(words)

    return dict(counter.most_common(limit))


def detect_complaints(reviews):

    complaints = []

    complaint_keywords = [
        "bad","slow","rude","dirty","expensive",
        "late","poor","terrible","worst","disappointed"
    ]

    for r in reviews:

        if r.sentiment_score < 0:

            for word in complaint_keywords:

                if word in (r.text or "").lower():
                    complaints.append(word)

    counter = Counter(complaints)

    return dict(counter.most_common(10))


# ---------------------------------------------------------
# DASHBOARD ANALYTICS API
# ---------------------------------------------------------

@router.get("/summary")
async def dashboard_summary(

    company_id: int = Query(...),

    start: Optional[date] = Query(None),

    end: Optional[date] = Query(None),

    group: str = Query("day"),

    limit: int = Query(50),

    session: AsyncSession = Depends(get_session)

):

    base_query = select(Review).where(Review.company_id == company_id)

    if start:
        base_query = base_query.where(Review.review_time >= start)

    if end:
        base_query = base_query.where(Review.review_time <= end)

    result = await session.execute(base_query)

    reviews = result.scalars().all()

    total_reviews = len(reviews)

    avg_rating = (
        sum(r.rating for r in reviews) / total_reviews
        if total_reviews else 0
    )

    positive = len([r for r in reviews if r.sentiment_score > 0])
    neutral = len([r for r in reviews if r.sentiment_score == 0])
    negative = len([r for r in reviews if r.sentiment_score < 0])


    # -----------------------------------------------------
    # RATING DISTRIBUTION
    # -----------------------------------------------------

    rating_distribution = {1:0,2:0,3:0,4:0,5:0}

    for r in reviews:

        rating_distribution[round(r.rating)] += 1


    # -----------------------------------------------------
    # SENTIMENT DISTRIBUTION
    # -----------------------------------------------------

    sentiment_distribution = {
        "positive": positive,
        "neutral": neutral,
        "negative": negative
    }


    # -----------------------------------------------------
    # REVIEW TREND
    # -----------------------------------------------------

    trend: Dict[str,int] = {}

    for r in reviews:

        if group == "month":
            key = r.review_time.strftime("%Y-%m")

        elif group == "week":
            key = r.review_time.strftime("%Y-W%U")

        else:
            key = r.review_time.isoformat()

        trend[key] = trend.get(key,0) + 1


    # -----------------------------------------------------
    # KEYWORD ANALYSIS
    # -----------------------------------------------------

    texts = [r.text for r in reviews if r.text]

    keywords = extract_keywords(texts)


    # -----------------------------------------------------
    # COMPLAINT DETECTION
    # -----------------------------------------------------

    complaints = detect_complaints(reviews)


    # -----------------------------------------------------
    # TOP REVIEWERS
    # -----------------------------------------------------

    author_counter = Counter([r.author_name for r in reviews if r.author_name])

    top_reviewers = dict(author_counter.most_common(10))


    # -----------------------------------------------------
    # LATEST REVIEWS (LIMIT BASED ON USER SELECTION)
    # -----------------------------------------------------

    latest_query = (
        select(
            Review.author_name,
            Review.rating,
            Review.sentiment_score,
            Review.review_time,
            Review.text
        )
        .where(Review.company_id == company_id)
        .order_by(desc(Review.review_time))
        .limit(limit)
    )

    latest_result = await session.execute(latest_query)

    latest_reviews = [

        {
            "author_name": row.author_name,
            "rating": row.rating,
            "sentiment_score": row.sentiment_score,
            "review_time": row.review_time.isoformat(),
            "text": row.text
        }

        for row in latest_result

    ]


    # -----------------------------------------------------
    # REPUTATION SCORE
    # -----------------------------------------------------

    reputation_score = round(
        (avg_rating * 20) +
        ((positive / total_reviews) * 20 if total_reviews else 0),
        2
    )


    # -----------------------------------------------------
    # FINAL RESPONSE
    # -----------------------------------------------------

    response = {

        "kpi":{

            "total_reviews": total_reviews,

            "avg_rating": round(avg_rating,2),

            "positive": positive,

            "neutral": neutral,

            "negative": negative,

            "reputation_score": reputation_score

        },

        "rating_distribution": rating_distribution,

        "sentiment_distribution": sentiment_distribution,

        "trend": trend,

        "keywords": keywords,

        "complaints": complaints,

        "top_reviewers": top_reviewers,

        "latest_reviews": latest_reviews

    }

    return JSONResponse(response)
