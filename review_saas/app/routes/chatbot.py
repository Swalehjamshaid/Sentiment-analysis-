# ==========================================================
# FILE: review_saas/app/routes/chatbot.py
# ENTERPRISE AI BUSINESS INTELLIGENCE CHATBOT
# 10/10 ENTERPRISE UPGRADE
# ==========================================================

import os
import re
import json
import time
import asyncio
import logging
from collections import Counter
from functools import lru_cache
from typing import List, Dict, Any

import numpy as np

from fastapi import (
    APIRouter,
    Request,
    Depends
)

from fastapi.responses import JSONResponse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from groq import Groq

from transformers import pipeline

from sentence_transformers import SentenceTransformer

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.db import get_session

from app.core.models import (
    Company,
    Review,
    ChatHistory
)

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(__name__)

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(
    prefix="/chatbot",
    tags=["Enterprise AI Chatbot"]
)

# ==========================================================
# ENVIRONMENT
# ==========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:

    logger.error("❌ GROQ_API_KEY missing")

# ==========================================================
# GROQ CLIENT
# ==========================================================

client = Groq(
    api_key=GROQ_API_KEY
)

logger.info("✅ Groq initialized")

# ==========================================================
# EMBEDDING MODEL
# ==========================================================

embedding_model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

logger.info("✅ Embedding model loaded")

# ==========================================================
# SENTIMENT MODEL
# ==========================================================

sentiment_pipeline = pipeline(
    "sentiment-analysis",
    model="cardiffnlp/twitter-roberta-base-sentiment"
)

logger.info("✅ Transformer sentiment model loaded")

# ==========================================================
# MEMORY CACHE
# ==========================================================

embedding_cache = {}

# ==========================================================
# TEXT CLEANING
# ==========================================================

def clean_text(text: str):

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
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()

# ==========================================================
# SENTIMENT ANALYSIS
# ==========================================================

def analyze_sentiment(text: str):

    try:

        result = sentiment_pipeline(text[:512])[0]

        label = result["label"]

        if label == "LABEL_2":
            return "Positive"

        elif label == "LABEL_0":
            return "Negative"

        return "Neutral"

    except Exception as e:

        logger.error(f"❌ Sentiment Error: {e}")

        return "Neutral"

# ==========================================================
# EMOTION DETECTION
# ==========================================================

def detect_emotion(text: str):

    text = text.lower()

    emotions = {

        "Anger": [
            "worst",
            "hate",
            "awful",
            "terrible",
            "fraud",
            "rude"
        ],

        "Frustration": [
            "late",
            "delay",
            "problem",
            "issue",
            "slow"
        ],

        "Satisfaction": [
            "great",
            "excellent",
            "perfect",
            "amazing",
            "good"
        ],

        "Disappointment": [
            "bad",
            "poor",
            "broken",
            "damaged"
        ]

    }

    for emotion, words in emotions.items():

        if any(word in text for word in words):

            return emotion

    return "Neutral"

# ==========================================================
# ISSUE CATEGORY
# ==========================================================

def categorize_issue(text: str):

    text = text.lower()

    categories = {

        "Delivery Issues": [
            "delivery",
            "late",
            "delay",
            "shipment"
        ],

        "Staff Behavior": [
            "staff",
            "employee",
            "rude",
            "attitude"
        ],

        "Product Quality": [
            "quality",
            "broken",
            "damaged",
            "poor"
        ],

        "Customer Support": [
            "support",
            "refund",
            "response"
        ],

        "Pricing Issues": [
            "price",
            "expensive",
            "cost"
        ]

    }

    for category, words in categories.items():

        if any(word in text for word in words):

            return category

    return "General"

# ==========================================================
# KEYWORD EXTRACTION
# ==========================================================

def detect_keywords(reviews: List[str]):

    issue_words = [

        "late",
        "delay",
        "broken",
        "damaged",
        "poor",
        "slow",
        "refund",
        "staff",
        "support",
        "quality",
        "delivery",
        "issue",
        "problem",
        "rude",
        "fraud",
        "expensive"

    ]

    keywords = []

    for review in reviews:

        for word in issue_words:

            if word in review:

                keywords.append(word)

    return Counter(keywords).most_common(10)

# ==========================================================
# EMBEDDING CACHE
# ==========================================================

def get_review_embeddings(company_id, review_texts):

    cache_key = f"company_{company_id}"

    if cache_key in embedding_cache:

        return embedding_cache[cache_key]

    embeddings = embedding_model.encode(
        review_texts,
        show_progress_bar=False
    )

    embedding_cache[cache_key] = embeddings

    return embeddings

# ==========================================================
# SEMANTIC SEARCH
# ==========================================================

def semantic_search(
    company_id,
    query,
    reviews
):

    try:

        review_texts = [

            r.text

            for r in reviews

            if r.text

        ]

        if not review_texts:

            return []

        review_embeddings = get_review_embeddings(
            company_id,
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

                "text":
                    review_texts[idx],

                "score":
                    round(float(similarities[idx]), 4)

            })

        return results

    except Exception as e:

        logger.error(f"❌ Semantic Search Error: {e}")

        return []

# ==========================================================
# ACTION PLANS
# ==========================================================

def generate_action_plans(keywords):

    actions = []

    for issue, count in keywords:

        if issue in [
            "late",
            "delay",
            "delivery"
        ]:

            actions.append({

                "priority": "High",

                "action":
                    "Optimize dispatch planning and increase fleet efficiency."

            })

        elif issue in [
            "staff",
            "rude"
        ]:

            actions.append({

                "priority": "Medium",

                "action":
                    "Conduct customer service training for staff."

            })

        elif issue in [
            "broken",
            "damaged",
            "quality"
        ]:

            actions.append({

                "priority": "High",

                "action":
                    "Strengthen product quality inspection processes."

            })

        elif issue in [
            "refund",
            "support"
        ]:

            actions.append({

                "priority": "Medium",

                "action":
                    "Improve customer support response speed."

            })

    return actions

# ==========================================================
# REPUTATION SCORE
# ==========================================================

def calculate_reputation_score(
    avg_rating,
    negative_reviews
):

    score = (
        (avg_rating / 5) * 100
    ) - (negative_reviews * 1.5)

    score = max(0, min(100, score))

    return round(score, 2)

# ==========================================================
# REVENUE RISK
# ==========================================================

def calculate_revenue_risk(
    negative_reviews,
    total_reviews
):

    if total_reviews == 0:
        return 0

    risk = (
        negative_reviews / total_reviews
    ) * 100

    return round(risk, 2)

# ==========================================================
# AI CONFIDENCE
# ==========================================================

def calculate_confidence(similarities):

    if not similarities:
        return 70

    avg = np.mean(similarities)

    return round(min(99, max(70, avg * 100)), 2)

# ==========================================================
# EXECUTIVE INSIGHTS
# ==========================================================

def generate_executive_insights(

    avg_rating,
    reputation_score,
    revenue_risk,
    negative_count

):

    insights = []

    if avg_rating < 3.5:

        insights.append(
            "Customer satisfaction is below industry expectations."
        )

    if revenue_risk > 30:

        insights.append(
            "High revenue risk detected from negative customer sentiment."
        )

    if reputation_score < 60:

        insights.append(
            "Brand reputation requires urgent operational improvements."
        )

    if negative_count > 50:

        insights.append(
            "Large volume of negative feedback indicates systemic issues."
        )

    return insights

# ==========================================================
# CHATBOT ENDPOINT
# ==========================================================

@router.post("/chat")

async def chatbot_api(

    request: Request,

    session: AsyncSession = Depends(
        get_session
    )

):

    start_time = time.time()

    try:

        body = await request.json()

        company_id = body.get("company_id")

        user_message = body.get(
            "message",
            ""
        ).strip()

        session_id = body.get(
            "session_id",
            "default_session"
        )

        # ==================================================
        # VALIDATION
        # ==================================================

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

        # ==================================================
        # LOAD COMPANY
        # ==================================================

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

        # ==================================================
        # LOAD CHAT MEMORY
        # ==================================================

        memory_stmt = (

            select(ChatHistory)

            .where(
                ChatHistory.session_id == session_id
            )

            .order_by(
                ChatHistory.created_at.desc()
            )

            .limit(10)

        )

        memory_result = await session.execute(
            memory_stmt
        )

        memory_rows = memory_result.scalars().all()

        previous_context = "\n".join([

            f"User: {m.user_message}\nAI: {m.ai_response}"

            for m in reversed(memory_rows)

        ])

        # ==================================================
        # LOAD REVIEWS
        # ==================================================

        review_stmt = (

            select(Review)

            .where(
                Review.company_id == int(company_id)
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
                    "No reviews available."

            })

        # ==================================================
        # PROCESS REVIEWS
        # ==================================================

        review_texts = []

        sentiments = []

        emotions = []

        categories = []

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

                emotions.append(
                    detect_emotion(cleaned)
                )

                categories.append(
                    categorize_issue(cleaned)
                )

                if review.rating:

                    ratings.append(
                        review.rating
                    )

        # ==================================================
        # ANALYTICS
        # ==================================================

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

        top_categories = Counter(
            categories
        ).most_common(5)

        top_emotions = Counter(
            emotions
        ).most_common(5)

        reputation_score = calculate_reputation_score(
            avg_rating,
            negative_count
        )

        revenue_risk = calculate_revenue_risk(
            negative_count,
            total_reviews
        )

        executive_insights = generate_executive_insights(

            avg_rating,
            reputation_score,
            revenue_risk,
            negative_count

        )

        semantic_results = semantic_search(

            company.id,
            user_message,
            reviews

        )

        confidence_score = calculate_confidence([

            r["score"]

            for r in semantic_results

        ])

        action_plans = generate_action_plans(
            top_keywords
        )

        # ==================================================
        # AI CONTEXT
        # ==================================================

        similar_reviews = "\n\n".join([

            f"- {r['text']}"

            for r in semantic_results

        ])

        issue_summary = "\n".join([

            f"{k}: {v}"

            for k, v in top_keywords

        ])

        emotion_summary = "\n".join([

            f"{k}: {v}"

            for k, v in top_emotions

        ])

        category_summary = "\n".join([

            f"{k}: {v}"

            for k, v in top_categories

        ])

        action_summary = "\n".join([

            f"{x['priority']} Priority: {x['action']}"

            for x in action_plans

        ])

        executive_summary = "\n".join(
            executive_insights
        )

        # ==================================================
        # PROMPT
        # ==================================================

        prompt = f"""

You are a world-class AI Business Intelligence Consultant.

Your job is to provide executive-level operational intelligence using ONLY review-based evidence.

==================================================

COMPANY:
{company.name}

==================================================

BUSINESS METRICS

Total Reviews:
{total_reviews}

Average Rating:
{avg_rating}

Reputation Score:
{reputation_score}

Revenue Risk:
{revenue_risk}%

Confidence Score:
{confidence_score}%

==================================================

CUSTOMER SENTIMENT

Positive:
{positive_count}

Negative:
{negative_count}

Neutral:
{neutral_count}

==================================================

TOP ISSUES

{issue_summary}

==================================================

ISSUE CATEGORIES

{category_summary}

==================================================

CUSTOMER EMOTIONS

{emotion_summary}

==================================================

EXECUTIVE INSIGHTS

{executive_summary}

==================================================

ACTION PLANS

{action_summary}

==================================================

RELEVANT REVIEWS

{similar_reviews}

==================================================

CHAT HISTORY

{previous_context}

==================================================

USER QUESTION

{user_message}

==================================================

RESPONSE RULES

1. Be executive-level
2. Be concise
3. Use business intelligence reasoning
4. Mention operational risks
5. Mention customer behavior patterns
6. Give strategic recommendations
7. Use bullet points when needed
8. Avoid hallucinations
9. Use only review evidence
10. Provide highly intelligent analysis

"""

        # ==================================================
        # AI RESPONSE
        # ==================================================

        response = client.chat.completions.create(

            model="llama-3.3-70b-versatile",

            messages=[

                {
                    "role": "system",

                    "content":
                        "You are an elite enterprise AI business intelligence advisor specializing in operational intelligence, executive reporting, customer sentiment analytics, risk analysis, predictive business insights, and strategic optimization."
                },

                {
                    "role": "user",

                    "content": prompt
                }

            ],

            temperature=0.2,

            max_tokens=1200

        )

        answer = (

            response
            .choices[0]
            .message
            .content

        )

        # ==================================================
        # SAVE MEMORY
        # ==================================================

        memory = ChatHistory(

            session_id=session_id,

            company_id=company.id,

            user_message=user_message,

            ai_response=answer

        )

        session.add(memory)

        await session.commit()

        # ==================================================
        # PERFORMANCE
        # ==================================================

        processing_time = round(
            time.time() - start_time,
            2
        )

        # ==================================================
        # FINAL RESPONSE
        # ==================================================

        return JSONResponse({

            "success": True,

            "company":
                company.name,

            "total_reviews":
                total_reviews,

            "average_rating":
                avg_rating,

            "positive_reviews":
                positive_count,

            "negative_reviews":
                negative_count,

            "neutral_reviews":
                neutral_count,

            "reputation_score":
                reputation_score,

            "revenue_risk":
                revenue_risk,

            "confidence_score":
                confidence_score,

            "processing_time":
                processing_time,

            "top_issues":
                top_keywords,

            "issue_categories":
                top_categories,

            "customer_emotions":
                top_emotions,

            "executive_insights":
                executive_insights,

            "ai_action_plans":
                action_plans,

            "semantic_matches":
                semantic_results,

            "answer":
                answer

        })

    except Exception as e:

        logger.error(
            f"🔥 ENTERPRISE CHATBOT ERROR: {e}"
        )

        return JSONResponse({

            "success": False,

            "answer":
                f"Enterprise AI Error: {str(e)}"

        }, status_code=500)
