# ==========================================================

# FILE: app/routes/chatbot.py

# WORLD-CLASS ENTERPRISE AI CHATBOT

# HUMAN-LIKE • FAST • ADAPTIVE • EXECUTIVE AI

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

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from vaderSentiment.vaderSentiment import (
SentimentIntensityAnalyzer
)

from groq import Groq

from app.core.db import get_session

from app.core.models import (
Company,
Review,
ChatHistory
)

# ==========================================================

# NEW ENTERPRISE AI SERVICES

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

GROQ_API_KEY = os.getenv(
"GROQ_API_KEY"
)

if not GROQ_API_KEY:
logger.error(
"❌ GROQ_API_KEY missing"
)

# ==========================================================

# GROQ CLIENT

# ==========================================================

client = Groq(
api_key=GROQ_API_KEY
)

logger.info(
"✅ Groq initialized"
)

# ==========================================================

# SENTIMENT ANALYZER

# ==========================================================

sentiment_analyzer = SentimentIntensityAnalyzer()

logger.info(
"✅ VADER Sentiment Analyzer Loaded"
)

# ==========================================================

# ENTERPRISE CACHE

# ==========================================================

cache = cache_service

# ==========================================================

# TEXT CLEANING

# ==========================================================

def clean_text(text: str) -> str:

```
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
```

# ==========================================================

# SENTIMENT ANALYSIS

# ==========================================================

def analyze_sentiment(text: str):

```
try:

    score = sentiment_analyzer.polarity_scores(text)

    compound = score["compound"]

    if compound >= 0.2:
        return "Positive"

    elif compound <= -0.2:
        return "Negative"

    return "Neutral"

except Exception as e:

    logger.error(
        f"❌ Sentiment Error: {e}"
    )

    return "Neutral"
```

# ==========================================================

# EMOTION DETECTION

# ==========================================================

def detect_emotion(text: str):

```
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
```

# ==========================================================

# ISSUE CATEGORY

# ==========================================================

def categorize_issue(text: str):

```
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
```

# ==========================================================

# KEYWORD EXTRACTION

# ==========================================================

def detect_keywords(reviews: List[str]):

```
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
```

# ==========================================================

# SEMANTIC SEARCH

# ==========================================================

def semantic_search(
company_id,
query,
reviews
):

```
try:

    cache_key = f"semantic_{company_id}_{query}"

    cached = cache.get(cache_key)

    if cached:
        return cached

    review_texts = [

        r.text

        for r in reviews

        if r.text and len(r.text.strip()) > 5

    ]

    if not review_texts:
        return []

    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_features=2500
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
    )[-7:][::-1]

    results = []

    for idx in top_indices:

        if similarities[idx] > 0:

            results.append({

                "text":
                    review_texts[idx],

                "score":
                    round(float(similarities[idx]), 4)

            })

    cache.set(
        cache_key,
        results,
        ttl=1800
    )

    return results

except Exception as e:

    logger.error(
        f"❌ Semantic Search Error: {e}"
    )

    return []
```

# ==========================================================

# ACTION PLANS

# ==========================================================

def generate_action_plans(keywords):

```
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
                "Improve dispatch routing and optimize logistics planning."

        })

    elif issue in [
        "staff",
        "rude"
    ]:

        actions.append({

            "priority": "Medium",

            "action":
                "Conduct customer service training and staff monitoring."

        })

    elif issue in [
        "broken",
        "damaged",
        "quality"
    ]:

        actions.append({

            "priority": "High",

            "action":
                "Strengthen quality control and packaging inspections."

        })

    elif issue in [
        "refund",
        "support"
    ]:

        actions.append({

            "priority": "Medium",

            "action":
                "Improve support response time and escalation handling."

        })

return actions
```

# ==========================================================

# REPUTATION SCORE

# ==========================================================

def calculate_reputation_score(
avg_rating,
negative_reviews
):

```
score = (
    (avg_rating / 5) * 100
) - (negative_reviews * 1.2)

score = max(0, min(100, score))

return round(score, 2)
```

# ==========================================================

# REVENUE RISK

# ==========================================================

def calculate_revenue_risk(
negative_reviews,
total_reviews
):

```
if total_reviews == 0:
    return 0

risk = (
    negative_reviews / total_reviews
) * 100

return round(risk, 2)
```

# ==========================================================

# CONFIDENCE SCORE

# ==========================================================

def calculate_confidence(similarities):

```
if not similarities:
    return 75

avg = np.mean(similarities)

return round(
    min(99, max(70, avg * 100)),
    2
)
```

# ==========================================================

# EXECUTIVE INSIGHTS

# ==========================================================

def generate_executive_insights(

```
avg_rating,
reputation_score,
revenue_risk,
negative_count
```

):

```
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

if negative_count > 40:

    insights.append(
        "High volume of negative reviews indicates operational instability."
    )

if not insights:

    insights.append(
        "Operational performance indicators remain relatively stable."
    )

return insights
```

# ==========================================================

# SMART REVIEW SAMPLING

# ==========================================================

def smart_review_sampling(
reviews,
limit=120
):

```
positive = []
negative = []
neutral = []

for review in reviews:

    if not review.text:
        continue

    sentiment = analyze_sentiment(review.text)

    if sentiment == "Positive":
        positive.append(review)

    elif sentiment == "Negative":
        negative.append(review)

    else:
        neutral.append(review)

selected = (

    negative[:50] +

    positive[:40] +

    neutral[:30]

)

return selected[:limit]
```

# ==========================================================

# DYNAMIC RESPONSE MODE

# ==========================================================

def build_response_instruction(response_mode):

```
if response_mode == "SHORT_MODE":

    return (
        "Respond naturally in 1-2 short human-like sentences only."
    )

elif response_mode == "BULLET_MODE":

    return (
        "Respond using concise bullet points only."
    )

elif response_mode == "EXECUTIVE_MODE":

    return (
        "Provide executive-level strategic analysis with business intelligence reasoning."
    )

elif response_mode == "SUMMARY_MODE":

    return (
        "Provide a concise business summary."
    )

elif response_mode == "ISSUE_MODE":

    return (
        "Focus only on the main customer issues and complaints."
    )

elif response_mode == "RECOMMENDATION_MODE":

    return (
        "Provide practical business recommendations only."
    )

return (
    "Respond naturally, conversationally, and professionally."
)
```

# ==========================================================

# CHATBOT ENDPOINT

# ==========================================================

@router.post("/chat")

async def chatbot_api(

```
request: Request,

session: AsyncSession = Depends(
    get_session
)
```

):

```
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

            "success": False,

            "answer":
                "Please select a company."

        })

    if not user_message:

        return JSONResponse({

            "success": False,

            "answer":
                "Please enter a message."

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
    # CACHE CHECK
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

            "success": False,

            "answer":
                "Company not found."

        })

    # ==================================================
    # MEMORY CONTEXT
    # ==================================================

    previous_context = memory_service.build_context(
        session_id=session_id,
        limit=6
    )

    contextual_query = memory_service.build_contextual_query(
        session_id=session_id,
        current_query=user_message
    )

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

        .limit(200)

    )

    review_result = await session.execute(
        review_stmt
    )

    all_reviews = review_result.scalars().all()

    if not all_reviews:

        return JSONResponse({

            "success": False,

            "answer":
                "No reviews available."

        })

    # ==================================================
    # SMART REVIEW SAMPLING
    # ==================================================

    reviews = await run_in_threadpool(
        smart_review_sampling,
        all_reviews
    )

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

            sentiment = analyze_sentiment(
                cleaned
            )

            sentiments.append(
                sentiment
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

    semantic_results = await run_in_threadpool(

        semantic_search,

        company.id,
        contextual_query,
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
    # SUMMARIES
    # ==================================================

    similar_reviews = "\n".join([

        f"- {r['text'][:220]}"

        for r in semantic_results[:5]

    ])

    issue_summary = "\n".join([

        f"{k}: {v}"

        for k, v in top_keywords

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
    # ENTERPRISE PROMPT
    # ==================================================

    prompt = f"""
```

You are a world-class enterprise AI business advisor.

Respond naturally like an intelligent human consultant.

==================================================

RESPONSE STYLE

{response_instruction}

==================================================

COMPANY:
{company.name}

==================================================

BUSINESS METRICS

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

RULES

1. Avoid robotic language
2. Sound natural and conversational
3. Be concise unless detailed analysis requested
4. Use only review evidence
5. Avoid hallucinations
6. Be intelligent and adaptive
7. Focus on actual customer feedback
8. Provide business reasoning when necessary
9. Keep responses human-like
10. Adapt response style to user intent

"""

```
    # ==================================================
    # AI RESPONSE
    # ==================================================

    response = await run_in_threadpool(

        lambda: client.chat.completions.create(

            model="llama-3.3-70b-versatile",

            messages=[

                {
                    "role": "system",

                    "content": (
                        "You are a highly intelligent, human-like enterprise AI business advisor."
                    )
                },

                {
                    "role": "user",

                    "content": prompt
                }

            ],

            temperature=0.3,

            max_tokens=900

        )

    )

    answer = (

        response
        .choices[0]
        .message
        .content

    )

    # ==================================================
    # HUMAN RESPONSE FORMATTER
    # ==================================================

    answer = response_formatter.format_chatbot_output(

        ai_response=answer,

        routing_data=routing_data

    )

    # ==================================================
    # SAVE DATABASE MEMORY
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
    # SAVE ENTERPRISE MEMORY
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
    # PERFORMANCE
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

        "response_mode":
            response_mode,

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
            answer,

        "cached":
            False

    }

    # ==================================================
    # SAVE CACHE
    # ==================================================

    cache.cache_chatbot_response(

        company_id,

        user_message,

        final_response

    )

    return JSONResponse(final_response)

except Exception as e:

    logger.error(
        f"🔥 ENTERPRISE CHATBOT ERROR: {e}"
    )

    return JSONResponse({

        "success": False,

        "answer":
            f"Enterprise AI Error: {str(e)}"

    }, status_code=500)
```
