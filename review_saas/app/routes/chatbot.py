# ==========================================================
# FILE: app/routes/chatbot.py
# TRUSTLYTICS AI — ENTERPRISE CHATBOT V2.0
# WITH VECTOR SEARCH, MULTI-MODEL ROUTING, STREAMING
# MAY 2026 - PRODUCTION READY
# ==========================================================

import os
import re
import time
import json
import logging
import asyncio
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np

from fastapi import (
    APIRouter,
    Request,
    Depends,
    HTTPException
)

from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.concurrency import run_in_threadpool

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

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
    ChatHistory,
    ChatSession
)

# ==========================================================
# SERVICES
# ==========================================================

from app.services.intent_router import intent_router
from app.services.memory_service import memory_service
from app.services.cache_service import cache_service
from app.services.response_formatter import response_formatter
from app.services.vector_service import vector_service  # NEW
from app.services.analytics_service import analytics_service  # NEW
from app.services.token_tracker import token_tracker  # NEW

# ==========================================================
# LOGGER
# ==========================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("✅ CHATBOT V2.0 LOGGER INITIALIZED")

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(
    prefix="/chatbot",
    tags=["Enterprise AI Chatbot V2"]
)

# ==========================================================
# ENVIRONMENT VARIABLES
# ==========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ENABLE_STREAMING = os.getenv("ENABLE_STREAMING", "true").lower() == "true"
ENABLE_COST_TRACKING = os.getenv("ENABLE_COST_TRACKING", "true").lower() == "true"

# ==========================================================
# GROQ CLIENT
# ==========================================================

client = None
try:
    if GROQ_API_KEY and GROQ_API_KEY.startswith("gsk_"):
        client = Groq(api_key=GROQ_API_KEY)
        logger.info("✅ GROQ CLIENT INITIALIZED")
    else:
        logger.warning("⚠️ INVALID GROQ_API_KEY")
except Exception as e:
    logger.error(f"❌ GROQ CLIENT FAILED: {e}")
    client = None

# ==========================================================
# PHASE 4: MULTI-MODEL AI ROUTER
# ==========================================================

class AIModelRouter:
    """Intelligent model selection based on query complexity"""
    
    MODEL_CONFIGS = {
        "fast": {
            "model": "llama-3.1-8b-instant",
            "max_tokens": 300,
            "temperature": 0.3,
            "cost_per_1k_tokens": 0.0002,
            "use_case": "short_qa"
        },
        "standard": {
            "model": "llama-3.3-70b-versatile",
            "max_tokens": 700,
            "temperature": 0.3,
            "cost_per_1k_tokens": 0.0008,
            "use_case": "business_analysis"
        },
        "executive": {
            "model": "deepseek-r1-distill-llama-70b",
            "max_tokens": 1500,
            "temperature": 0.4,
            "cost_per_1k_tokens": 0.0012,
            "use_case": "executive_report",
            "requires_api": "DEEPSEEK_API_KEY"
        }
    }
    
    def __init__(self):
        self.deepseek_available = bool(DEEPSEEK_API_KEY)
        self.openai_available = bool(OPENAI_API_KEY)
    
    def select_model(self, query: str, response_mode: str) -> Dict[str, Any]:
        """Select best model based on query complexity and mode"""
        
        # Executive mode gets executive model
        if response_mode == "EXECUTIVE_MODE" and self.deepseek_available:
            return self.MODEL_CONFIGS["executive"]
        
        # Short mode gets fast model
        if response_mode == "SHORT_MODE":
            return self.MODEL_CONFIGS["fast"]
        
        # Check query complexity
        word_count = len(query.split())
        has_numbers = bool(re.search(r'\d+', query))
        has_comparison = any(word in query.lower() for word in ["compare", "versus", "vs", "difference"])
        
        if word_count > 20 or has_numbers or has_comparison:
            return self.MODEL_CONFIGS["standard"]
        
        return self.MODEL_CONFIGS["fast"]
    
    async def generate_response(
        self, 
        prompt: str, 
        model_config: Dict[str, Any],
        session_id: str
    ) -> Tuple[str, Dict[str, Any]]:
        """Generate response using selected model"""
        
        start_time = time.time()
        model_name = model_config["model"]
        
        try:
            # Check if using DeepSeek
            if "deepseek" in model_name and self.deepseek_available:
                # Use DeepSeek API (simplified)
                response = await self._call_deepseek(prompt, model_config)
            else:
                # Use Groq
                response = await run_in_threadpool(
                    lambda: client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": "You are a highly intelligent enterprise AI advisor."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=model_config["temperature"],
                        max_tokens=model_config["max_tokens"]
                    )
                )
                response_text = response.choices[0].message.content
            
            # Track tokens
            if ENABLE_COST_TRACKING:
                input_tokens = len(prompt.split())
                output_tokens = len(response_text.split())
                cost = (input_tokens / 1000) * model_config["cost_per_1k_tokens"] + \
                       (output_tokens / 1000) * model_config["cost_per_1k_tokens"]
                
                token_tracker.track_usage(
                    session_id=session_id,
                    model=model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=cost,
                    duration=time.time() - start_time
                )
            
            return response_text, {
                "model_used": model_name,
                "duration": round(time.time() - start_time, 2),
                "use_case": model_config["use_case"]
            }
            
        except Exception as e:
            logger.error(f"Model generation error: {e}")
            # Fallback to standard model
            fallback_config = self.MODEL_CONFIGS["standard"]
            return await self.generate_response(prompt, fallback_config, session_id)
    
    async def _call_deepseek(self, prompt: str, config: Dict) -> str:
        """Call DeepSeek API"""
        # Simplified - implement actual DeepSeek API call
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                json={
                    "model": config["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": config["temperature"],
                    "max_tokens": config["max_tokens"]
                },
                timeout=30.0
            )
            data = response.json()
            return data["choices"][0]["message"]["content"]

model_router = AIModelRouter()

# ==========================================================
# PHASE 3: PROMPT SANITIZER
# ==========================================================

class PromptSanitizer:
    """Protect against prompt injection attacks"""
    
    DANGEROUS_PATTERNS = [
        r"ignore previous instructions",
        r"ignore all instructions",
        r"system prompt",
        r"reveal your prompt",
        r"show your system message",
        r"print your system prompt",
        r"what is your system prompt",
        r"how were you trained",
        r"api[_\s]*key",
        r"secret[_\s]*key",
        r"authorization[_\s]*token",
        r"bypass[_\s]*security",
        r"hack[_\s]*the[_\s]*system",
        r"<script",
        r"javascript:",
        r"onclick=",
        r"eval\("
    ]
    
    @staticmethod
    def sanitize(query: str) -> Tuple[bool, str]:
        """Check if query is safe, return (is_safe, reason)"""
        
        query_lower = query.lower()
        
        for pattern in PromptSanitizer.DANGEROUS_PATTERNS:
            if re.search(pattern, query_lower):
                logger.warning(f"🚨 PROMPT INJECTION DETECTED: {pattern}")
                return False, f"Security policy violation: {pattern}"
        
        # Check length
        if len(query) > 2000:
            return False, "Query exceeds maximum length (2000 chars)"
        
        # Check for excessive special characters
        special_chars = sum(not c.isalnum() and not c.isspace() for c in query)
        if special_chars > 100:
            return False, "Too many special characters"
        
        return True, "safe"
    
    @staticmethod
    def escape_markdown(text: str) -> str:
        """Escape markdown characters to prevent injection"""
        markdown_chars = ['*', '_', '`', '[', ']', '(', ')', '#', '+', '-', '.', '!', '\\']
        for char in markdown_chars:
            text = text.replace(char, f'\\{char}')
        return text

prompt_sanitizer = PromptSanitizer()

# ==========================================================
# PHASE 5: STREAMING RESPONSE
# ==========================================================

async def stream_response(generator, session_id: str):
    """Stream AI response token by token"""
    try:
        async for chunk in generator:
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

# ==========================================================
# SENTIMENT ANALYZER
# ==========================================================

try:
    sentiment_analyzer = SentimentIntensityAnalyzer()
    logger.info("✅ SENTIMENT ANALYZER READY")
except Exception as e:
    logger.error(f"❌ SENTIMENT ANALYZER FAILED: {e}")
    sentiment_analyzer = None

# ==========================================================
# PHASE 1: PRE-COMPUTED ANALYTICS
# ==========================================================

async def get_precomputed_analytics(company_id: int, session: AsyncSession) -> Dict[str, Any]:
    """Get precomputed analytics from database (no re-computation)"""
    
    # Check cache first
    cache_key = f"analytics:company:{company_id}"
    cached = cache_service.get(cache_key)
    if cached:
        return cached
    
    # Query precomputed aggregates
    result = await session.execute(
        select(
            func.avg(Review.sentiment_score).label("avg_sentiment"),
            func.count(Review.id).label("total_reviews"),
            func.sum(func.cast(Review.sentiment_score > 0.2, func.integer)).label("positive_count"),
            func.sum(func.cast(Review.sentiment_score < -0.2, func.integer)).label("negative_count"),
            func.avg(Review.rating).label("avg_rating")
        ).where(Review.company_id == company_id)
    )
    
    stats = result.one()
    
    # Get precomputed keywords from database
    keyword_result = await session.execute(
        select(Review.top_keywords)
        .where(Review.company_id == company_id, Review.top_keywords.isnot(None))
        .limit(50)
    )
    
    all_keywords = []
    for row in keyword_result:
        if row[0]:
            all_keywords.extend(json.loads(row[0]) if isinstance(row[0], str) else row[0])
    
    top_keywords = Counter(all_keywords).most_common(10)
    
    # Get precomputed categories
    category_result = await session.execute(
        select(Review.category, func.count(Review.id))
        .where(Review.company_id == company_id, Review.category.isnot(None))
        .group_by(Review.category)
        .order_by(func.count(Review.id).desc())
        .limit(5)
    )
    
    top_categories = [(row[0], row[1]) for row in category_result]
    
    analytics = {
        "average_rating": round(float(stats.avg_rating or 0), 2),
        "total_reviews": stats.total_reviews or 0,
        "positive_count": stats.positive_count or 0,
        "negative_count": stats.negative_count or 0,
        "neutral_count": (stats.total_reviews or 0) - (stats.positive_count or 0) - (stats.negative_count or 0),
        "average_sentiment": round(float(stats.avg_sentiment or 0), 3),
        "top_keywords": top_keywords,
        "top_categories": top_categories
    }
    
    # Cache for 5 minutes
    cache_service.set(cache_key, analytics, ttl=300)
    
    return analytics

# ==========================================================
# PHASE 2: VECTOR SEMANTIC SEARCH
# ==========================================================

async def vector_semantic_search(
    query: str,
    company_id: int,
    session: AsyncSession,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """Vector-based semantic search using embeddings"""
    
    # Try vector search first
    if vector_service.is_available:
        try:
            results = await vector_service.similarity_search(
                query=query,
                company_id=company_id,
                top_k=top_k
            )
            if results:
                return results
        except Exception as e:
            logger.warning(f"Vector search failed, falling back to TF-IDF: {e}")
    
    # Fallback to TF-IDF
    reviews = await session.execute(
        select(Review.text, Review.rating)
        .where(Review.company_id == company_id, Review.text.isnot(None))
        .limit(200)
    )
    
    review_list = [(r.text, r.rating) for r in reviews]
    
    if not review_list:
        return []
    
    # Simple keyword matching as fallback
    query_words = set(query.lower().split())
    scored_reviews = []
    
    for text, rating in review_list:
        if not text:
            continue
        text_lower = text.lower()
        matches = sum(1 for word in query_words if word in text_lower)
        if matches > 0:
            scored_reviews.append({
                "text": text[:300],
                "rating": rating,
                "score": matches / len(query_words) if query_words else 0
            })
    
    scored_reviews.sort(key=lambda x: x["score"], reverse=True)
    return scored_reviews[:top_k]

# ==========================================================
# PHASE 6: CHAT SESSION INTELLIGENCE
# ==========================================================

class ChatSessionManager:
    """Intelligent session management with long-term memory"""
    
    def __init__(self):
        self.active_sessions = {}
    
    async def get_or_create_session(
        self, 
        session_id: str, 
        company_id: int,
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """Get or create chat session with intelligence"""
        
        # Check in-memory
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]
        
        # Check database
        result = await db_session.execute(
            select(ChatSession)
            .where(ChatSession.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            session = ChatSession(
                session_id=session_id,
                company_id=company_id,
                session_summary="",
                known_issues=[],
                business_goals=[],
                created_at=datetime.utcnow()
            )
            db_session.add(session)
            await db_session.commit()
        
        session_data = {
            "id": session.id,
            "session_id": session.session_id,
            "company_id": session.company_id,
            "session_summary": session.session_summary or "",
            "known_issues": json.loads(session.known_issues) if session.known_issues else [],
            "business_goals": json.loads(session.business_goals) if session.business_goals else [],
            "customer_trends": json.loads(session.customer_trends) if session.customer_trends else []
        }
        
        self.active_sessions[session_id] = session_data
        return session_data
    
    async def update_session_intelligence(
        self,
        session_id: str,
        query: str,
        response: str,
        db_session: AsyncSession
    ):
        """Update session with learned intelligence"""
        
        session_data = await self.get_or_create_session(session_id, 0, db_session)
        
        # Extract potential issues
        query_lower = query.lower()
        potential_issues = []
        
        issue_keywords = {
            "delivery": ["delivery", "shipping", "courier"],
            "support": ["support", "refund", "customer service"],
            "quality": ["quality", "broken", "damaged"],
            "staff": ["staff", "employee", "rude"],
            "pricing": ["price", "cost", "expensive"]
        }
        
        for issue, keywords in issue_keywords.items():
            if any(k in query_lower for k in keywords):
                potential_issues.append(issue)
        
        # Update known issues
        for issue in potential_issues:
            if issue not in session_data["known_issues"]:
                session_data["known_issues"].append(issue)
        
        # Update database
        await db_session.execute(
            update(ChatSession)
            .where(ChatSession.session_id == session_id)
            .values(
                known_issues=json.dumps(session_data["known_issues"]),
                last_active=datetime.utcnow()
            )
        )
        await db_session.commit()

session_manager = ChatSessionManager()

# ==========================================================
# CLEAN TEXT (Preserved)
# ==========================================================

def clean_text(text: str) -> str:
    try:
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r"http\S+", "", text)
        text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    except Exception as e:
        logger.error(f"❌ CLEAN TEXT ERROR: {e}")
        return ""

# ==========================================================
# LEGACY FUNCTIONS (Preserved for compatibility)
# ==========================================================

def analyze_sentiment(text: str) -> str:
    try:
        if not sentiment_analyzer:
            return "Neutral"
        score = sentiment_analyzer.polarity_scores(text)
        compound = score["compound"]
        if compound >= 0.2:
            return "Positive"
        if compound <= -0.2:
            return "Negative"
        return "Neutral"
    except Exception as error:
        logger.error(f"❌ SENTIMENT ERROR: {error}")
        return "Neutral"

def detect_emotion(text: str) -> str:
    try:
        text = text.lower()
        emotions = {
            "Anger": ["worst", "hate", "terrible", "awful", "fraud"],
            "Frustration": ["delay", "late", "problem", "slow"],
            "Satisfaction": ["great", "excellent", "perfect", "good"],
            "Disappointment": ["poor", "bad", "broken", "damaged"]
        }
        for emotion, words in emotions.items():
            if any(word in text for word in words):
                return emotion
        return "Neutral"
    except Exception as e:
        logger.error(f"❌ EMOTION ERROR: {e}")
        return "Neutral"

def categorize_issue(text: str) -> str:
    try:
        text = text.lower()
        categories = {
            "Delivery": ["delivery", "late", "delay"],
            "Support": ["support", "refund", "response"],
            "Quality": ["quality", "broken", "damaged"],
            "Staff": ["staff", "employee", "rude"],
            "Pricing": ["price", "cost", "expensive"]
        }
        for category, words in categories.items():
            if any(word in text for word in words):
                return category
        return "General"
    except Exception as e:
        logger.error(f"❌ CATEGORY ERROR: {e}")
        return "General"

def build_response_instruction(response_mode: str) -> str:
    if response_mode == "SHORT_MODE":
        return "Respond briefly and naturally."
    if response_mode == "BULLET_MODE":
        return "Respond using concise bullet points."
    if response_mode == "EXECUTIVE_MODE":
        return "Provide executive-level strategic analysis."
    return "Respond professionally and conversationally."

# ==========================================================
# PHASE 10: EXECUTIVE INTELLIGENCE LAYER
# ==========================================================

async def generate_executive_insights(
    company_name: str,
    analytics: Dict[str, Any],
    reviews: List[Review],
    session: AsyncSession
) -> Dict[str, Any]:
    """Generate business intelligence insights"""
    
    # Calculate risk scores
    negative_percentage = (analytics["negative_count"] / max(1, analytics["total_reviews"])) * 100
    
    risk_scores = {
        "customer_churn_risk": min(100, negative_percentage * 1.5),
        "brand_reputation_risk": min(100, negative_percentage * 1.2),
        "operational_risk": min(100, negative_percentage),
        "revenue_impact_score": min(100, negative_percentage * 0.8)
    }
    
    # Determine risk level
    avg_risk = sum(risk_scores.values()) / 4
    if avg_risk > 70:
        risk_level = "Critical"
    elif avg_risk > 40:
        risk_level = "Elevated"
    else:
        risk_level = "Low"
    
    # Find top concerns from reviews
    all_text = " ".join([r.text for r in reviews if r.text])[:5000]
    concern_keywords = ["delay", "broken", "rude", "expensive", "poor", "slow", "refund"]
    
    top_concerns = []
    for keyword in concern_keywords:
        count = all_text.lower().count(keyword)
        if count > 0:
            top_concerns.append({"concern": keyword, "mentions": count})
    
    top_concerns.sort(key=lambda x: x["mentions"], reverse=True)
    
    return {
        "risk_scores": risk_scores,
        "overall_risk_level": risk_level,
        "top_concerns": top_concerns[:5],
        "recommendations": _generate_recommendations(risk_scores, top_concerns),
        "executive_summary": _generate_executive_summary(company_name, analytics, risk_level)
    }

def _generate_recommendations(risk_scores: Dict, concerns: List) -> List[str]:
    recommendations = []
    
    if risk_scores["customer_churn_risk"] > 50:
        recommendations.append("Launch customer retention campaign immediately")
    
    if risk_scores["brand_reputation_risk"] > 40:
        recommendations.append("Increase social media monitoring and response rate")
    
    if concerns and concerns[0]["mentions"] > 5:
        recommendations.append(f"Prioritize fixing {concerns[0]['concern']} issues")
    
    if not recommendations:
        recommendations.append("Maintain current positive trajectory")
    
    return recommendations[:3]

def _generate_executive_summary(company_name: str, analytics: Dict, risk_level: str) -> str:
    return f"""{company_name} shows {analytics['positive_count']} positive vs {analytics['negative_count']} negative reviews. 
Overall rating: {analytics['average_rating']}/5. Risk level: {risk_level}. 
Top areas: {', '.join([k for k, v in analytics['top_keywords'][:3]])}."""

# ==========================================================
# MAIN CHATBOT ENDPOINT
# ==========================================================

@router.post("/chat")
async def chatbot_api(
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    start_time = time.time()
    
    try:
        # GROQ CHECK
        if not client:
            return JSONResponse({
                "success": False,
                "answer": "GROQ AI service unavailable."
            }, status_code=500)
        
        # REQUEST BODY
        body = await request.json()
        company_id = body.get("company_id")
        user_message = body.get("message", "").strip()
        session_id = body.get("session_id", "default_session")
        stream = body.get("stream", ENABLE_STREAMING)
        
        # VALIDATION
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
        
        # PHASE 3: PROMPT SANITIZER
        is_safe, reason = prompt_sanitizer.sanitize(user_message)
        if not is_safe:
            logger.warning(f"Rejected unsafe query: {reason}")
            return JSONResponse({
                "success": False,
                "answer": f"I cannot process that request. {reason}"
            }, status_code=400)
        
        # INTENT ROUTING
        routing_data = intent_router.detect_intent(user_message)
        response_mode = routing_data.get("response_mode", "NORMAL_MODE")
        response_instruction = build_response_instruction(response_mode)
        
        # CACHE CHECK
        cached_response = cache_service.get_chatbot_response(company_id, user_message)
        if cached_response:
            cached_response["cached"] = True
            return JSONResponse(cached_response)
        
        # GET COMPANY
        company_query = select(Company).where(Company.id == int(company_id))
        company_result = await session.execute(company_query)
        company = company_result.scalar_one_or_none()
        
        if not company:
            return JSONResponse({
                "success": False,
                "answer": "Company not found."
            })
        
        # PHASE 1: USE PRECOMPUTED ANALYTICS
        analytics = await get_precomputed_analytics(int(company_id), session)
        
        # GET REVIEWS FOR DEEP ANALYSIS
        review_query = (
            select(Review)
            .where(Review.company_id == int(company_id))
            .limit(100)
        )
        review_result = await session.execute(review_query)
        reviews = review_result.scalars().all()
        
        # PHASE 2: VECTOR SEMANTIC SEARCH
        semantic_results = await vector_semantic_search(
            query=user_message,
            company_id=int(company_id),
            session=session,
            top_k=5
        )
        
        # PHASE 6: SESSION INTELLIGENCE
        session_data = await session_manager.get_or_create_session(
            session_id=session_id,
            company_id=int(company_id),
            db_session=session
        )
        
        # MEMORY CONTEXT
        previous_context = memory_service.build_context(
            session_id=session_id,
            limit=5
        )
        
        contextual_query = memory_service.build_contextual_query(
            session_id=session_id,
            current_query=user_message
        )
        
        # BUILD SIMILAR REVIEWS TEXT
        similar_reviews = "\n".join([
            f"- {item['text'][:220]}"
            for item in semantic_results
        ])
        
        # PHASE 10: EXECUTIVE INSIGHTS
        executive_insights = {}
        if response_mode == "EXECUTIVE_MODE":
            executive_insights = await generate_executive_insights(
                company_name=company.name,
                analytics=analytics,
                reviews=reviews,
                session=session
            )
        
        # BUILD PROMPT
        prompt = f"""
You are a world-class enterprise AI advisor.

RESPONSE STYLE:
{response_instruction}

COMPANY:
{company.name}

AVERAGE RATING:
{analytics['average_rating']}

POSITIVE REVIEWS:
{analytics['positive_count']}

NEGATIVE REVIEWS:
{analytics['negative_count']}

NEUTRAL REVIEWS:
{analytics['neutral_count']}

TOP ISSUES:
{analytics['top_keywords']}

TOP CATEGORIES:
{analytics['top_categories']}

PREVIOUS CONTEXT:
{previous_context}

SIMILAR REVIEWS:
{similar_reviews}
"""

        # Add executive insights if in executive mode
        if executive_insights:
            prompt += f"""
EXECUTIVE INSIGHTS:
Risk Scores: {executive_insights['risk_scores']}
Risk Level: {executive_insights['overall_risk_level']}
Top Concerns: {executive_insights['top_concerns']}
Recommendations: {executive_insights['recommendations']}
Executive Summary: {executive_insights['executive_summary']}
"""

        prompt += f"""
USER QUESTION:
{user_message}

Respond professionally and naturally.
"""
        
        # PHASE 4: SELECT AND USE MODEL
        model_config = model_router.select_model(user_message, response_mode)
        
        # PHASE 5: HANDLE STREAMING
        if stream:
            async def generate():
                response_text, metadata = await model_router.generate_response(
                    prompt, model_config, session_id
                )
                # Stream response in chunks
                chunk_size = 50
                for i in range(0, len(response_text), chunk_size):
                    yield response_text[i:i+chunk_size]
                    await asyncio.sleep(0.05)
            
            return StreamingResponse(
                stream_response(generate(), session_id),
                media_type="text/event-stream"
            )
        
        # NON-STREAMING RESPONSE
        answer, model_metadata = await model_router.generate_response(
            prompt, model_config, session_id
        )
        
        # FORMAT RESPONSE
        answer = response_formatter.format_chatbot_output(
            ai_response=answer,
            routing_data=routing_data
        )
        
        # UPDATE SESSION INTELLIGENCE
        await session_manager.update_session_intelligence(
            session_id=session_id,
            query=user_message,
            response=answer,
            db_session=session
        )
        
        # SAVE CHAT HISTORY
        chat_memory = ChatHistory(
            session_id=session_id,
            company_id=company.id,
            user_message=user_message,
            ai_response=answer
        )
        session.add(chat_memory)
        await session.commit()
        
        # MEMORY SERVICE
        memory_service.add_memory(
            session_id=session_id,
            user_message=user_message,
            ai_response=answer,
            metadata={
                "company_id": company_id,
                "mode": response_mode,
                "model_used": model_metadata["model_used"]
            }
        )
        
        processing_time = round(time.time() - start_time, 2)
        
        # FINAL RESPONSE
        final_response = {
            "success": True,
            "company": company.name,
            "average_rating": analytics["average_rating"],
            "positive_reviews": analytics["positive_count"],
            "negative_reviews": analytics["negative_count"],
            "neutral_reviews": analytics["neutral_count"],
            "top_issues": analytics["top_keywords"],
            "top_categories": analytics["top_categories"],
            "semantic_matches": semantic_results,
            "response_mode": response_mode,
            "model_used": model_metadata["model_used"],
            "model_duration": model_metadata["duration"],
            "processing_time": processing_time,
            "answer": answer,
            "cached": False
        }
        
        # Add executive insights if available
        if executive_insights:
            final_response["executive_insights"] = executive_insights
        
        # CACHE RESPONSE
        cache_service.cache_chatbot_response(company_id, user_message, final_response)
        
        return JSONResponse(final_response)
        
    except Exception as error:
        logger.error(f"❌ ENTERPRISE CHATBOT ERROR: {error}")
        logger.error(traceback.format_exc())
        return JSONResponse({
            "success": False,
            "answer": f"Enterprise AI Error: {str(error)}"
        }, status_code=500)

# ==========================================================
# PHASE 7: ENTERPRISE HEALTH MONITORING
# ==========================================================

@router.get("/health")
async def chatbot_health():
    """Enhanced health check with enterprise metrics"""
    
    health_data = {
        "status": "healthy",
        "groq_connected": bool(client),
        "deepseek_connected": bool(DEEPSEEK_API_KEY),
        "vector_store": vector_service.is_available,
        "service": "enterprise_chatbot_v2",
        "version": "2.0.0",
        "features": {
            "streaming": ENABLE_STREAMING,
            "cost_tracking": ENABLE_COST_TRACKING,
            "vector_search": vector_service.is_available,
            "executive_insights": True,
            "multi_model_routing": True
        }
    }
    
    # Add performance metrics if tracking
    if ENABLE_COST_TRACKING:
        health_data["cost_metrics"] = token_tracker.get_summary()
    
    # Add cache metrics
    health_data["cache_metrics"] = cache_service.get_metrics()
    
    # Add active sessions count
    health_data["active_sessions"] = len(session_manager.active_sessions)
    
    return JSONResponse(health_data)

# ==========================================================
# PHASE 9: RESPONSE QUALITY ENDPOINT
# ==========================================================

@router.post("/feedback")
async def submit_feedback(request: Request):
    """Collect feedback on response quality"""
    
    body = await request.json()
    session_id = body.get("session_id")
    response_id = body.get("response_id")
    quality_score = body.get("quality_score")  # 1-5
    relevance_score = body.get("relevance_score")  # 1-5
    hallucination_detected = body.get("hallucination_detected", False)
    
    # Store feedback for model improvement
    token_tracker.record_feedback(
        session_id=session_id,
        quality_score=quality_score,
        relevance_score=relevance_score,
        hallucination_detected=hallucination_detected
    )
    
    return JSONResponse({
        "success": True,
        "message": "Feedback recorded"
    })

# ==========================================================
# PHASE 8: COST TRACKING ENDPOINT
# ==========================================================

@router.get("/costs")
async def get_cost_metrics():
    """Get AI cost tracking metrics"""
    
    if not ENABLE_COST_TRACKING:
        return JSONResponse({
            "success": False,
            "message": "Cost tracking not enabled"
        })
    
    summary = token_tracker.get_summary()
    return JSONResponse({
        "success": True,
        "metrics": summary
    })
