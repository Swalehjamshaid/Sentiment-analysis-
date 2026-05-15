# ==========================================================
# FILE: review_saas/app/routes/chatbot.py
# ENTERPRISE AI BUSINESS INTELLIGENCE CHATBOT
# ==========================================================

import os
import re
import logging
from collections import Counter
from typing import List, Dict

import numpy as np

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

from app.core.db import get_session

from app.core.models import (
    Company,
    Review,
    ChatHistory
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
# GROQ AI CONFIG
# ==========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:

    logger.error(
        "❌ GROQ_API_KEY missing"
    )

client = Groq(
    api_key=GROQ_API_KEY
)

logger.info(
    "✅ Groq AI initialized successfully"
)

# ==========================================================
# EMBEDDING MODEL
# ==========================================================

embedding_model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

logger.info(
    "✅ Embedding model loaded"
)

# ==========================================================
# HELPERS
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

def detect_emotion(text: str):

    text = text.lower()

    anger_words = [
        "worst",
        "hate",
        "fraud",
        "awful",
        "terrible",
        "rude"
    ]

    frustration_words = [
        "late",
        "delay",
        "slow",
        "problem",
        "issue"
    ]

    satisfaction_words = [
        "good",
        "great",
        "excellent",
        "perfect",
        "amazing"
    ]

    if any(word in text for word in anger_words):
        return "Anger"

    if any(word in text for word in frustration_words):
        return "Frustration"

    if any(word in text for word in satisfaction_words):
        return "Satisfaction"

    return "Neutral"

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

def categorize_issue(review_text):

    review_text = review_text.lower()

    categories = {

        "Delivery Issues": [
            "late",
            "delay",
            "delivery",
            "shipment",
            "dispatch"
        ],

        "Staff Behavior": [
            "staff",
            "rude",
            "behavior",
            "employee",
            "attitude"
        ],

        "Product Quality": [
            "damaged",
            "broken",
            "quality",
            "poor",
            "defect"
        ],

        "Customer Support": [
            "support",
            "refund",
            "response",
            "service"
        ],

        "Cleanliness": [
            "dirty",
            "clean",
            "hygiene"
        ]
    }

    for category, words in categories.items():

        if any(word in review_text for word in words):
            return category

    return "General"

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
        )[-5:][::-1]

        results = []

        for idx in top_indices:

            results.append({

                "text":
                    review_texts[idx],

                "score":
                    float(similarities[idx])

            })

        return results

    except Exception as e:

        logger.error(
            f"❌ Semantic Search Error: {e}"
        )

        return []

# ==========================================================

def generate_action_plans(top_keywords):

    actions = []

    for issue, count in top_keywords:

        if issue in [
            "late",
            "delay",
            "delivery"
        ]:

            actions.append(
                "Increase delivery fleet capacity and optimize dispatch planning."
            )

        elif issue in [
            "staff",
            "rude"
        ]:

            actions.append(
                "Conduct staff behavior and customer service training."
            )

        elif issue in [
            "damaged",
            "broken",
            "quality"
        ]:

            actions.append(
                "Improve quality assurance and packaging inspection."
            )

        elif issue in [
            "refund",
            "support"
        ]:

            actions.append(
                "Enhance customer support response speed and escalation handling."
            )

    return list(set(actions))

# ==========================================================

def calculate_reputation_score(avg_rating, negative_reviews):

    try:

        reputation = (
            (avg_rating / 5) * 100
        ) - (negative_reviews * 1.5)

        reputation = max(
            0,
            min(100, reputation)
        )

        return round(reputation, 2)

    except:
        return 0

# ==========================================================

def calculate_revenue_risk(
    negative_reviews,
    total_reviews
):

    try:

        if total_reviews == 0:
            return 0

        risk = (
            negative_reviews / total_reviews
        ) * 100

        return round(risk, 2)

    except:
        return 0

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
        # LOAD MEMORY
        # ==================================================

        memory_stmt = (

            select(ChatHistory)

            .where(
                ChatHistory.session_id == session_id
            )

            .order_by(
                ChatHistory.created_at.desc()
            )

            .limit(5)

        )

        memory_result = await session.execute(
            memory_stmt
        )

        memory_rows = memory_result.scalars().all()

        previous_context = "\n".join([

            f"User: {x.user_message}\nAI: {x.ai_response}"

            for x in reversed(memory_rows)

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

            .limit(300)

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

        issue_categories = []

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

                issue_categories.append(
                    categorize_issue(cleaned)
                )

                if review.rating:
                    ratings.append(
                        review.rating
                    )

        # ==================================================
        # METRICS
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

        top_categories = Counter(
            issue_categories
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

        # ==================================================
        # CLUSTERING
        # ==================================================

        review_clusters = cluster_reviews(
            review_texts
        )

        # ==================================================
        # SEMANTIC SEARCH
        # ==================================================

        semantic_results = semantic_search(
            user_message,
            reviews
        )

        # ==================================================
        # AI ACTION PLANS
        # ==================================================

        action_plans = generate_action_plans(
            top_keywords
        )

        # ==================================================
        # SUMMARIES
        # ==================================================

        issue_summary = "\n".join([

            f"{word}: {count}"

            for word, count in top_keywords

        ])

        category_summary = "\n".join([

            f"{cat}: {count}"

            for cat, count in top_categories

        ])

        emotion_summary = "\n".join([

            f"{emo}: {count}"

            for emo, count in top_emotions

        ])

        action_plan_summary = "\n".join(
            action_plans
        )

        similar_reviews = "\n\n".join([

            r["text"]

            for r in semantic_results

        ])

        # ==================================================
        # EXECUTIVE PROMPT
        # ==================================================

        prompt = f"""

You are a world-class AI business intelligence consultant.

Company:
{company.name}

Total Reviews:
{total_reviews}

Average Rating:
{avg_rating}

Reputation Score:
{reputation_score}

Revenue Risk:
{revenue_risk}%

Positive Reviews:
{positive_count}

Negative Reviews:
{negative_count}

Neutral Reviews:
{neutral_count}

Top Issues:
{issue_summary}

Issue Categories:
{category_summary}

Customer Emotions:
{emotion_summary}

AI Recommended Actions:
{action_plan_summary}

Relevant Customer Reviews:
{similar_reviews}

Previous Conversation:
{previous_context}

User Question:
{user_message}

Instructions:

1. Answer professionally.
2. Use business intelligence reasoning.
3. Give executive-level analysis.
4. Explain root causes.
5. Provide actionable recommendations.
6. Mention operational risks if needed.
7. Mention customer sentiment patterns.
8. Keep response highly intelligent.
9. Be concise but insightful.
10. Only answer using review-based insights.

"""

        # ==================================================
        # GROQ AI RESPONSE
        # ==================================================

        response = client.chat.completions.create(

            model="llama-3.3-70b-versatile",

            messages=[

                {
                    "role": "system",
                    "content":
                        "You are an elite AI business intelligence consultant specializing in customer review analytics, operational intelligence, executive reporting, root-cause analysis, predictive analytics, and business decision intelligence."
                },

                {
                    "role": "user",
                    "content": prompt
                }

            ],

            temperature=0.3,

            max_tokens=700

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

        chat_memory = ChatHistory(

            session_id=session_id,

            company_id=company.id,

            user_message=user_message,

            ai_response=answer

        )

        session.add(
            chat_memory
        )

        await session.commit()

        # ==================================================
        # FINAL RESPONSE
        # ==================================================

        return JSONResponse({

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

            "top_issues":
                top_keywords,

            "issue_categories":
                top_categories,

            "customer_emotions":
                top_emotions,

            "review_clusters":
                review_clusters,

            "ai_action_plans":
                action_plans,

            "semantic_matches":
                semantic_results,

            "answer":
                answer

        })

    except Exception as e:

        logger.error(
            f"🔥 Chatbot Error: {e}"
        )

        return JSONResponse({

            "answer":
                f"Server Error: {str(e)}"

        }, status_code=500)
