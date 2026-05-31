# ==========================================================
# FILE: app/routes/chatbot.py
# TRUSTLYTICS AI — FINAL STABLE ENTERPRISE CHATBOT
# MAY 2026 RAILWAY SAFE VERSION
# ==========================================================

import os
import re
import time
import logging

from collections import Counter
from typing import List

import numpy as np

from fastapi import (
    APIRouter,
    Request,
    Depends
)

from fastapi.responses import JSONResponse

from fastapi.concurrency import run_in_threadpool

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from sklearn.feature_extraction.text import (
    TfidfVectorizer
)

from sklearn.metrics.pairwise import (
    cosine_similarity
)

from vaderSentiment.vaderSentiment import (
    SentimentIntensityAnalyzer
)

from groq import Groq

# ==========================================================
# DATABASE
# ==========================================================

from app.core.db import get_session

# ==========================================================
# MODELS
# ==========================================================

from app.core.models import (
    Company,
    Review,
    ChatHistory
)

# ==========================================================
# SERVICES
# ==========================================================

from app.services.intent_router import (
    intent_router
)

from app.services.memory_service import (
    memory_service
)

from app.services.cache_service import (
    cache_service
)

from app.services.response_formatter import (
    response_formatter
)

# ==========================================================
# LOGGER
# ==========================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

logger.info("✅ CHATBOT LOGGER INITIALIZED")

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(

    prefix="/chatbot",

    tags=["Enterprise AI Chatbot"]
)

# ==========================================================
# ENVIRONMENT VARIABLES
# ==========================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

# ==========================================================
# SAFE GROQ CLIENT INITIALIZATION
# ==========================================================

client = None

try:

    if GROQ_API_KEY and GROQ_API_KEY.startswith("gsk_"):

        client = Groq(
            api_key=GROQ_API_KEY
        )

        logger.info(
            "✅ GROQ CLIENT INITIALIZED"
        )

    else:

        logger.warning(
            "⚠️ INVALID OR MISSING GROQ_API_KEY"
        )

except Exception as e:

    logger.error(
        f"❌ GROQ CLIENT INIT FAILED: {e}"
    )

    client = None

# ==========================================================
# SENTIMENT ANALYZER
# ==========================================================

try:

    sentiment_analyzer = SentimentIntensityAnalyzer()

    logger.info(
        "✅ SENTIMENT ANALYZER READY"
    )

except Exception as e:

    logger.error(
        f"❌ SENTIMENT ANALYZER FAILED: {e}"
    )

    sentiment_analyzer = None

# ==========================================================
# CACHE
# ==========================================================

cache = cache_service

# ==========================================================
# CLEAN TEXT
# ==========================================================

def clean_text(text: str) -> str:

    try:

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

    except Exception as e:

        logger.error(
            f"❌ CLEAN TEXT ERROR: {e}"
        )

        return ""

# ==========================================================
# SENTIMENT ANALYSIS
# ==========================================================

def analyze_sentiment(text: str) -> str:

    try:

        if not sentiment_analyzer:
            return "Neutral"

        score = sentiment_analyzer.polarity_scores(
            text
        )

        compound = score["compound"]

        if compound >= 0.2:
            return "Positive"

        if compound <= -0.2:
            return "Negative"

        return "Neutral"

    except Exception as error:

        logger.error(
            f"❌ SENTIMENT ERROR: {error}"
        )

        return "Neutral"

# ==========================================================
# DETECT EMOTION
# ==========================================================

def detect_emotion(text: str) -> str:

    try:

        text = text.lower()

        emotions = {

            "Anger": [
                "worst",
                "hate",
                "terrible",
                "awful",
                "fraud"
            ],

            "Frustration": [
                "delay",
                "late",
                "problem",
                "slow"
            ],

            "Satisfaction": [
                "great",
                "excellent",
                "perfect",
                "good"
            ],

            "Disappointment": [
                "poor",
                "bad",
                "broken",
                "damaged"
            ]
        }

        for emotion, words in emotions.items():

            if any(word in text for word in words):

                return emotion

        return "Neutral"

    except Exception as e:

        logger.error(
            f"❌ EMOTION DETECTION ERROR: {e}"
        )

        return "Neutral"

# ==========================================================
# ISSUE CATEGORY
# ==========================================================

def categorize_issue(text: str) -> str:

    try:

        text = text.lower()

        categories = {

            "Delivery": [
                "delivery",
                "late",
                "delay"
            ],

            "Support": [
                "support",
                "refund",
                "response"
            ],

            "Quality": [
                "quality",
                "broken",
                "damaged"
            ],

            "Staff": [
                "staff",
                "employee",
                "rude"
            ],

            "Pricing": [
                "price",
                "cost",
                "expensive"
            ]
        }

        for category, words in categories.items():

            if any(word in text for word in words):

                return category

        return "General"

    except Exception as e:

        logger.error(
            f"❌ CATEGORY ERROR: {e}"
        )

        return "General"

# ==========================================================
# KEYWORD EXTRACTION
# ==========================================================

def detect_keywords(reviews: List[str]):

    try:

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
            "expensive"
        ]

        keywords = []

        for review in reviews:

            for word in issue_words:

                if word in review:

                    keywords.append(word)

        return Counter(keywords).most_common(10)

    except Exception as e:

        logger.error(
            f"❌ KEYWORD ERROR: {e}"
        )

        return []

# ==========================================================
# SEMANTIC SEARCH
# ==========================================================

def semantic_search(

    query: str,

    reviews: List[Review]
):

    try:

        review_texts = [

            r.text

            for r in reviews

            if r.text and len(r.text.strip()) > 5
        ]

        if not review_texts:

            return []

        vectorizer = TfidfVectorizer(

            stop_words="english",

            max_features=2000
        )

        vectors = vectorizer.fit_transform(

            review_texts + [query]
        )

        similarities = cosine_similarity(

            vectors[-1],

            vectors[:-1]
        )[0]

        top_indices = np.argsort(
            similarities
        )[-5:][::-1]

        results = []

        for idx in top_indices:

            if similarities[idx] > 0:

                results.append({

                    "text":
                        review_texts[idx],

                    "score":
                        round(float(similarities[idx]), 4)
                })

        return results

    except Exception as error:

        logger.error(
            f"❌ SEMANTIC SEARCH ERROR: {error}"
        )

        return []

# ==========================================================
# RESPONSE STYLE
# ==========================================================

def build_response_instruction(
    response_mode: str
) -> str:

    if response_mode == "SHORT_MODE":

        return "Respond briefly and naturally."

    if response_mode == "BULLET_MODE":

        return "Respond using concise bullet points."

    if response_mode == "EXECUTIVE_MODE":

        return "Provide executive-level strategic analysis."

    return "Respond professionally and conversationally."

# ==========================================================
# CHATBOT ENDPOINT
# ==========================================================

@router.post("/chat")

async def chatbot_api(

    request: Request,

    session: AsyncSession = Depends(get_session)
):

    start_time = time.time()

    try:

        # ==================================================
        # GROQ CHECK
        # ==================================================

        if not client:

            return JSONResponse({

                "success": False,

                "answer": "GROQ AI service unavailable."

            }, status_code=500)

        # ==================================================
        # REQUEST BODY
        # ==================================================

        body = await request.json()

        company_id = body.get(
            "company_id"
        )

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

                "success": False,

                "answer": "Please select a company."
            })

        if not user_message:

            return JSONResponse({

                "success": False,

                "answer": "Please enter a message."
            })

        # ==================================================
        # INTENT ROUTING
        # ==================================================

        routing_data = intent_router.detect_intent(
            user_message
        )

        response_mode = routing_data.get(

            "response_mode",

            "NORMAL_MODE"
        )

        response_instruction = build_response_instruction(
            response_mode
        )

        # ==================================================
        # CACHE
        # ==================================================

        cached_response = cache.get_chatbot_response(

            company_id,

            user_message
        )

        if cached_response:

            cached_response["cached"] = True

            return JSONResponse(
                cached_response
            )

        # ==================================================
        # COMPANY
        # ==================================================

        company_query = select(Company).where(

            Company.id == int(company_id)
        )

        company_result = await session.execute(
            company_query
        )

        company = company_result.scalar_one_or_none()

        if not company:

            return JSONResponse({

                "success": False,

                "answer": "Company not found."
            })

        # ==================================================
        # REVIEWS
        # ==================================================

        review_query = (

            select(Review)

            .where(
                Review.company_id == int(company_id)
            )

            .limit(150)
        )

        review_result = await session.execute(
            review_query
        )

        reviews = review_result.scalars().all()

        if not reviews:

            return JSONResponse({

                "success": False,

                "answer": "No reviews available."
            })

        # ==================================================
        # MEMORY CONTEXT
        # ==================================================

        previous_context = memory_service.build_context(

            session_id=session_id,

            limit=5
        )

        contextual_query = memory_service.build_contextual_query(

            session_id=session_id,

            current_query=user_message
        )

        # ==================================================
        # SEMANTIC SEARCH
        # ==================================================

        semantic_results = await run_in_threadpool(

            semantic_search,

            contextual_query,

            reviews
        )

        # ==================================================
        # ANALYTICS
        # ==================================================

        review_texts = [

            clean_text(r.text)

            for r in reviews

            if r.text
        ]

        sentiments = [

            analyze_sentiment(text)

            for text in review_texts
        ]

        emotions = [

            detect_emotion(text)

            for text in review_texts
        ]

        categories = [

            categorize_issue(text)

            for text in review_texts
        ]

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

        top_emotions = Counter(
            emotions
        ).most_common(5)

        top_categories = Counter(
            categories
        ).most_common(5)

        ratings = [

            r.rating

            for r in reviews

            if r.rating
        ]

        average_rating = round(

            sum(ratings) / max(1, len(ratings)),

            2
        )

        # ==================================================
        # SIMILAR REVIEWS
        # ==================================================

        similar_reviews = "\n".join([

            f"- {item['text'][:220]}"

            for item in semantic_results
        ])

        # ==================================================
        # PROMPT
        # ==================================================

        prompt = f"""
You are a world-class enterprise AI assistant.

RESPONSE STYLE:
{response_instruction}

COMPANY:
{company.name}

AVERAGE RATING:
{average_rating}

POSITIVE REVIEWS:
{positive_count}

NEGATIVE REVIEWS:
{negative_count}

NEUTRAL REVIEWS:
{neutral_count}

TOP ISSUES:
{top_keywords}

TOP CATEGORIES:
{top_categories}

TOP EMOTIONS:
{top_emotions}

PREVIOUS CONTEXT:
{previous_context}

SIMILAR REVIEWS:
{similar_reviews}

USER QUESTION:
{user_message}

Respond naturally and professionally.
"""

        # ==================================================
        # GROQ AI RESPONSE
        # ==================================================

        response = await run_in_threadpool(

            lambda: client.chat.completions.create(

                model="llama-3.3-70b-versatile",

                messages=[

                    {

                        "role": "system",

                        "content":
                            "You are a highly intelligent enterprise AI advisor."
                    },

                    {

                        "role": "user",

                        "content": prompt
                    }
                ],

                temperature=0.3,

                max_tokens=700
            )
        )

        answer = response.choices[0].message.content

        # ==================================================
        # FORMAT RESPONSE
        # ==================================================

        answer = response_formatter.format_chatbot_output(

            ai_response=answer,

            routing_data=routing_data
        )

        # ==================================================
        # SAVE CHAT
        # ==================================================

        chat_memory = ChatHistory(

            session_id=session_id,

            company_id=company.id,

            user_message=user_message,

            ai_response=answer
        )

        session.add(chat_memory)

        await session.commit()

        # ==================================================
        # MEMORY SERVICE
        # ==================================================

        memory_service.add_memory(

            session_id=session_id,

            user_message=user_message,

            ai_response=answer,

            metadata={

                "company_id": company_id,

                "mode": response_mode
            }
        )

        # ==================================================
        # PROCESSING TIME
        # ==================================================

        processing_time = round(

            time.time() - start_time,

            2
        )

        # ==================================================
        # FINAL RESPONSE
        # ==================================================

        final_response = {

            "success": True,

            "company": company.name,

            "average_rating": average_rating,

            "positive_reviews": positive_count,

            "negative_reviews": negative_count,

            "neutral_reviews": neutral_count,

            "top_issues": top_keywords,

            "top_categories": top_categories,

            "top_emotions": top_emotions,

            "semantic_matches": semantic_results,

            "response_mode": response_mode,

            "processing_time": processing_time,

            "answer": answer,

            "cached": False
        }

        # ==================================================
        # CACHE RESPONSE
        # ==================================================

        cache.cache_chatbot_response(

            company_id,

            user_message,

            final_response
        )

        return JSONResponse(
            final_response
        )

    except Exception as error:

        logger.error(
            f"❌ ENTERPRISE CHATBOT ERROR: {error}"
        )

        return JSONResponse({

            "success": False,

            "answer":
                f"Enterprise AI Error: {str(error)}"

        }, status_code=500)

# ==========================================================
# HEALTH CHECK
# ==========================================================

@router.get("/health")

async def chatbot_health():

    return {

        "status": "healthy",

        "groq_connected": bool(client),

        "service": "enterprise_chatbot"
    }
