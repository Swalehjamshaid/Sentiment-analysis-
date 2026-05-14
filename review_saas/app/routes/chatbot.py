# ==========================================================
# FILE: review_saas/app/routes/chatbot.py
# ==========================================================

import os
import re
import logging
from collections import Counter
from typing import List

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from groq import Groq

from textblob import TextBlob

from sentence_transformers import SentenceTransformer

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans

import numpy as np

from app.core.db import get_session
from app.core.models import Company, Review

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(
    prefix="/chatbot",
    tags=["AI Chatbot"]
)

logger = logging.getLogger(__name__)

# ==========================================================
# GROQ CONFIG
# ==========================================================

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

logger.info("✅ Groq AI initialized successfully")

# ==========================================================
# EMBEDDING MODEL
# ==========================================================

embedding_model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

# ==========================================================
# HELPERS
# ==========================================================

def clean_text(text: str):

    if not text:
        return ""

    text = text.lower()

    text = re.sub(r"http\S+", "", text)

    text = re.sub(
        r"[^a-zA-Z0-9\s]",
        "",
        text
    )

    return text.strip()

# ==========================================================

def analyze_sentiment(text: str):

    try:

        polarity = TextBlob(
            text
        ).sentiment.polarity

        if polarity > 0.2:
            return "Positive"

        elif polarity < -0.2:
            return "Negative"

        return "Neutral"

    except:
        return "Unknown"

# ==========================================================

def detect_keywords(reviews: List[str]):

    issue_words = [

        "late",
        "delay",
        "damaged",
        "broken",
        "bad",
        "poor",
        "slow",
        "refund",
        "staff",
        "service",
        "delivery",
        "support",
        "quality",
        "problem",
        "issue",
        "rude",
        "missing",
        "packaging",
        "cancel",
        "dirty",
        "fraud"

    ]

    keywords = []

    for review in reviews:

        for word in issue_words:

            if word in review.lower():
                keywords.append(word)

    return Counter(keywords).most_common(10)

# ==========================================================

def cluster_reviews(review_texts):

    try:

        if len(review_texts) < 5:
            return []

        vectorizer = TfidfVectorizer(
            stop_words="english"
        )

        X = vectorizer.fit_transform(
            review_texts
        )

        cluster_model = KMeans(
            n_clusters=min(5, len(review_texts)),
            random_state=42,
            n_init="auto"
        )

        cluster_model.fit(X)

        return cluster_model.labels_.tolist()

    except Exception as e:

        logger.error(
            f"❌ Clustering Error: {e}"
        )

        return []

# ==========================================================

def semantic_search(query, reviews):

    try:

        review_texts = [
            r.text for r in reviews if r.text
        ]

        if not review_texts:
            return []

        review_embeddings = embedding_model.encode(
            review_texts
        )

        query_embedding = embedding_model.encode(
            [query]
        )

        similarities = cosine_similarity(
            query_embedding,
            review_embeddings
        )[0]

        top_indices = np.argsort(
            similarities
        )[-2:][::-1]

        results = []

        for idx in top_indices:

            results.append({

                "text": review_texts[idx],

                "score": float(
                    similarities[idx]
                )

            })

        return results

    except Exception as e:

        logger.error(
            f"❌ Semantic Search Error: {e}"
        )

        return []

# ==========================================================
# CHATBOT API
# ==========================================================

@router.post("/chat")

async def chatbot_api(

    request: Request,

    session: AsyncSession = Depends(
        get_session
    )

):

    try:

        body = await request.json()

        company_id = body.get("company_id")

        user_message = body.get(
            "message",
            ""
        ).strip()

        if not company_id:

            return JSONResponse({

                "answer":
                    "Please select a company."

            })

        if not user_message:

            return JSONResponse({

                "answer":
                    "Please enter a message."

            })

        company_stmt = select(
            Company
        ).where(
            Company.id == int(company_id)
        )

        company_result = await session.execute(
            company_stmt
        )

        company = company_result.scalar_one_or_none()

        if not company:

            return JSONResponse({

                "answer":
                    "Company not found."

            })

        review_stmt = (

            select(Review)

            .where(
                Review.company_id == int(company_id)
            )

            .order_by(
                Review.google_review_time.desc()
            )

            .limit(10)

        )

        review_result = await session.execute(
            review_stmt
        )

        reviews = review_result.scalars().all()

        if not reviews:

            return JSONResponse({

                "answer":
                    "No reviews available."

            })

        review_texts = []

        sentiments = []

        ratings = []

        for review in reviews:

            if review.text:

                cleaned = clean_text(
                    review.text
                )

                review_texts.append(cleaned)

                sentiments.append(
                    analyze_sentiment(cleaned)
                )

                if review.rating:
                    ratings.append(review.rating)

        total_reviews = len(review_texts)

        avg_rating = round(
            sum(ratings) / len(ratings),
            2
        ) if ratings else 0

        positive_count = sentiments.count(
            "Positive"
        )

        negative_count = sentiments.count(
            "Negative"
        )

        neutral_count = sentiments.count(
            "Neutral"
        )

        top_keywords = detect_keywords(
            review_texts
        )

        semantic_results = semantic_search(
            user_message,
            reviews
        )

        issue_summary = "\n".join([

            f"{word}: {count}"

            for word, count in top_keywords

        ])

        similar_reviews = "\n\n".join([

            r["text"]

            for r in semantic_results

        ])

        prompt = f"""

Business:
{company.name}

Average Rating:
{avg_rating}

Positive Reviews:
{positive_count}

Negative Reviews:
{negative_count}

Top Issues:
{issue_summary}

Relevant Reviews:
{similar_reviews}

User Question:
{user_message}

Answer professionally and briefly
based only on customer reviews.
"""

        response = client.chat.completions.create(

            model="llama-3.3-70b-versatile",

            messages=[

                {
                    "role": "system",
                    "content":
                        "You are an expert business analyst."
                },

                {
                    "role": "user",
                    "content": prompt
                }

            ],

            temperature=0.3,

            max_tokens=300

        )

        answer = (
            response
            .choices[0]
            .message
            .content
        )

        return JSONResponse({

            "company": company.name,

            "total_reviews": total_reviews,

            "average_rating": avg_rating,

            "positive_reviews": positive_count,

            "negative_reviews": negative_count,

            "neutral_reviews": neutral_count,

            "top_issues": top_keywords,

            "answer": answer

        })

    except Exception as e:

        logger.error(
            f"🔥 Chatbot Error: {e}"
        )

        return JSONResponse({

            "answer":
                f"Server Error: {str(e)}"

        }, status_code=500)
