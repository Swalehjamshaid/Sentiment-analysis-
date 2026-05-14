# ==========================================================
# FILE: review_saas/app/routes/chatbot.py
# ==========================================================
# ENTERPRISE AI BUSINESS INTELLIGENCE CHATBOT
# ==========================================================
# FEATURES:
# ✅ PostgreSQL Integration
# ✅ Gemini AI
# ✅ Semantic Search
# ✅ Sentiment Analysis
# ✅ Intelligent Scope Detection
# ✅ Complaint Detection
# ✅ Trend Analysis
# ✅ Issue Clustering
# ✅ Business Intelligence
# ✅ Smart Recommendations
# ✅ Root Cause Analysis
# ✅ AI Memory-Like Context Search
# ==========================================================

import os
import re
import json
import logging
from collections import Counter
from typing import List

from fastapi import (
    APIRouter,
    Request,
    Depends
)

from fastapi.responses import JSONResponse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# ==========================================================
# AI / NLP LIBRARIES
# ==========================================================

import google.generativeai as genai

from textblob import TextBlob

from sentence_transformers import (
    SentenceTransformer
)

from sklearn.feature_extraction.text import (
    TfidfVectorizer
)

from sklearn.metrics.pairwise import (
    cosine_similarity
)

from sklearn.cluster import KMeans

import numpy as np

# ==========================================================
# DATABASE IMPORTS
# ==========================================================

from app.core.db import get_session

from app.core.models import (
    Company,
    Review
)

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(
    prefix="/chatbot",
    tags=["AI Chatbot"]
)

logger = logging.getLogger(__name__)

# ==========================================================
# GEMINI CONFIGURATION
# ==========================================================

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

model = None

try:

    genai.configure(
        api_key=GEMINI_API_KEY
    )

    model = genai.GenerativeModel(
        "gemini-1.5-flash"
    )

    logger.info(
        "✅ Gemini AI initialized successfully"
    )

except Exception as e:

    logger.error(
        f"❌ Gemini Initialization Error: {e}"
    )

# ==========================================================
# SENTENCE EMBEDDING MODEL
# ==========================================================

embedding_model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

# ==========================================================
# HELPER FUNCTIONS
# ==========================================================

def clean_text(text: str) -> str:

    if not text:
        return ""

    text = text.lower()

    text = re.sub(
        r"http\S+",
        "",
        text
    )

    text = re.sub(
        r"[^a-zA-Z0-9\s]",
        "",
        text
    )

    return text.strip()

# ==========================================================

def analyze_sentiment(text: str):

    try:

        analysis = TextBlob(text)

        polarity = analysis.sentiment.polarity

        if polarity > 0.2:
            return "Positive"

        elif polarity < -0.2:
            return "Negative"

        return "Neutral"

    except:
        return "Unknown"

# ==========================================================

def detect_keywords(reviews: List[str]):

    keywords = []

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
        "waiting",
        "problem",
        "issue",
        "rude",
        "expensive",
        "missing",
        "packaging",
        "cancel",
        "dirty",
        "fake",
        "cold",
        "hot",
        "fraud",
        "unprofessional",
        "behavior",
        "response"

    ]

    for review in reviews:

        review_lower = review.lower()

        for word in issue_words:

            if word in review_lower:
                keywords.append(word)

    counter = Counter(keywords)

    return counter.most_common(15)

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

        num_clusters = min(
            5,
            len(review_texts)
        )

        cluster_model = KMeans(
            n_clusters=num_clusters,
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
        )[-7:][::-1]

        results = []

        for idx in top_indices:

            results.append({
                "text": review_texts[idx],
                "score": float(similarities[idx])
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

        # ==================================================
        # REQUEST BODY
        # ==================================================

        body = await request.json()

        company_id_raw = body.get(
            "company_id"
        )

        user_message = body.get(
            "message",
            ""
        ).strip()

        # ==================================================
        # VALIDATION
        # ==================================================

        if not company_id_raw:

            return JSONResponse({

                "answer":
                    "Please select a company first."

            })

        if not user_message:

            return JSONResponse({

                "answer":
                    "Please enter a message."

            })

        try:

            company_id = int(
                company_id_raw
            )

        except:

            return JSONResponse({

                "answer":
                    "Invalid company ID."

            })

        # ==================================================
        # FETCH COMPANY
        # ==================================================

        company_stmt = select(
            Company
        ).where(
            Company.id == company_id
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

        # ==================================================
        # FETCH REVIEWS
        # ==================================================

        review_stmt = (

            select(Review)

            .where(
                Review.company_id == company_id
            )

            .order_by(
                Review.google_review_time.desc()
            )

            .limit(500)

        )

        review_result = await session.execute(
            review_stmt
        )

        reviews = review_result.scalars().all()

        if not reviews:

            return JSONResponse({

                "answer":
                    "No reviews found. Please sync reviews first."

            })

        # ==================================================
        # INTELLIGENT SCOPE DETECTION
        # ==================================================

        allowed_keywords = [

            "review",
            "rating",
            "customer",
            "complaint",
            "delivery",
            "service",
            "staff",
            "quality",
            "business",
            "issue",
            "problem",
            "feedback",
            "sentiment",
            "analysis",
            "product",
            "support",
            "refund",
            "packaging",
            "management",
            "company",
            "experience",
            "negative",
            "positive",
            "trend",
            "late",
            "damage",
            "behavior",
            "delay",
            "performance",
            "satisfaction"

        ]

        user_message_lower = user_message.lower()

        relevant = any(

            keyword in user_message_lower

            for keyword in allowed_keywords

        )

        if not relevant:

            return JSONResponse({

                "answer":
                    "AI Business Expert: This question is outside my business review analysis scope. Please ask questions related to customer reviews, ratings, complaints, delivery, service quality, staff behavior, support, packaging, operational issues, or business performance."

            })

        # ==================================================
        # REVIEW PROCESSING
        # ==================================================

        review_texts = []

        sentiments = []

        ratings = []

        for review in reviews:

            if review.text:

                cleaned = clean_text(
                    review.text
                )

                review_texts.append(
                    cleaned
                )

                sentiments.append(
                    analyze_sentiment(
                        cleaned
                    )
                )

                if review.rating:
                    ratings.append(
                        review.rating
                    )

        # ==================================================
        # BUSINESS STATISTICS
        # ==================================================

        total_reviews = len(
            review_texts
        )

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

        clusters = cluster_reviews(
            review_texts
        )

        semantic_results = semantic_search(

            user_message,

            reviews

        )

        # ==================================================
        # ISSUE SUMMARY
        # ==================================================

        issue_summary = "\n".join([

            f"{word}: {count} mentions"

            for word, count in top_keywords

        ])

        # ==================================================
        # SEMANTIC REVIEW MATCHES
        # ==================================================

        similar_reviews = "\n\n".join([

            f"Review: {r['text']}"

            for r in semantic_results

        ])

        # ==================================================
        # TREND ANALYSIS
        # ==================================================

        if negative_count > positive_count:

            trend = (
                "Customer satisfaction trend is negative."
            )

        elif positive_count > negative_count:

            trend = (
                "Customer satisfaction trend is positive."
            )

        else:

            trend = (
                "Customer sentiment trend is balanced."
            )

        # ==================================================
        # AI PROMPT
        # ==================================================

        prompt = f"""

You are one of the world's most advanced
AI Business Intelligence Experts.

Business Name:
{company.name}

BUSINESS ANALYTICS:

Total Reviews:
{total_reviews}

Average Rating:
{avg_rating}

Positive Reviews:
{positive_count}

Negative Reviews:
{negative_count}

Neutral Reviews:
{neutral_count}

Customer Trend:
{trend}

TOP REPORTED ISSUES:
{issue_summary}

MOST RELEVANT CUSTOMER REVIEWS:
{similar_reviews}

USER QUESTION:
{user_message}

YOUR RESPONSIBILITIES:

1. Analyze customer complaints
2. Detect operational issues
3. Detect delivery failures
4. Detect support problems
5. Detect product quality issues
6. Detect staff behavior issues
7. Detect recurring patterns
8. Explain root causes
9. Suggest intelligent solutions
10. Provide management insights
11. Answer professionally
12. Use business intelligence reasoning

IMPORTANT RULES:

- Base answer ONLY on review data
- Do NOT hallucinate
- Be analytical and intelligent
- Be concise but insightful
- Mention recurring issues
- Mention severity level
- Explain business impact
- Suggest practical improvements
- Be highly professional

"""

        # ==================================================
        # GEMINI AI RESPONSE
        # ==================================================

        try:

            response = model.generate_content(

                prompt,

                request_options={
                    "timeout": 60
                }

            )

            answer = None

            if (

                hasattr(response, "text")

                and response.text

            ):

                answer = response.text

            elif hasattr(response, "candidates"):

                try:

                    answer = (

                        response
                        .candidates[0]
                        .content
                        .parts[0]
                        .text

                    )

                except:
                    pass

            if not answer:

                answer = (
                    "AI could not generate a response."
                )

            # ==================================================
            # FINAL RESPONSE
            # ==================================================

            return JSONResponse({

                "company": company.name,

                "total_reviews": total_reviews,

                "average_rating": avg_rating,

                "positive_reviews": positive_count,

                "negative_reviews": negative_count,

                "neutral_reviews": neutral_count,

                "top_issues": top_keywords,

                "trend": trend,

                "answer": answer

            })

        except Exception as ai_error:

            logger.error(
                f"❌ AI Runtime Error: {ai_error}"
            )

            return JSONResponse({

                "answer":
                    "AI processing failed."

            })

    except Exception as e:

        logger.error(
            f"🔥 Chatbot Critical Error: {e}"
        )

        return JSONResponse({

            "answer":
                f"Server Error: {str(e)}"

        }, status_code=500)
