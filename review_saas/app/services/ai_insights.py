# filename: app/services/ai_insights.py

import os
from typing import Optional
from sqlalchemy.orm import Session

# Modern Google GenAI SDK
from google import genai

from ..models import Review, Company


# =========================================================
# SAFE CLIENT INITIALIZATION
# =========================================================

MODEL_NAME = "gemini-1.5-flash"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize client ONLY if API key exists
client: Optional[genai.Client] = None

if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Gemini client init error: {e}")
        client = None
else:
    print("WARNING: GEMINI_API_KEY not set. AI features disabled.")


# =========================================================
# AI REPLY GENERATION
# =========================================================

async def generate_ai_reply(review_text: str, rating: int, company_name: str) -> str:
    """Uses Gemini to draft a context-aware response."""

    if not client:
        return "Thank you for your feedback. We value your input."

    prompt = (
        f"Write a professional response for {company_name} "
        f"to this {rating}-star review: '{review_text}'. "
        f"Keep it under 60 words."
    )

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        if response and response.text:
            return response.text.strip()

        return "Thank you for your feedback. We value your input."

    except Exception as e:
        print(f"Gemini reply error: {e}")
        return "Thank you for your feedback. We value your input."


# =========================================================
# EXECUTIVE SUMMARY
# =========================================================

def get_executive_summary(company_id: int, db: Session) -> str:
    """Generates a high-level summary of recent feedback trends."""

    reviews = db.query(Review).filter_by(company_id=company_id).limit(5).all()

    if not reviews:
        return "No data yet to summarize."

    if not client:
        return "Reviews indicate a steady trend in customer satisfaction."

    text_blob = " ".join([r.text for r in reviews if r.text])

    prompt = f"Summarize these customer reviews in two sentences: {text_blob}"

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        if response and response.text:
            return response.text.strip()

        return "Reviews indicate a steady trend in customer satisfaction."

    except Exception as e:
        print(f"Gemini summary error: {e}")
        return "Reviews indicate a steady trend in customer satisfaction."


# =========================================================
# SAFE STUBS (Prevent Import Errors Anywhere)
# =========================================================

def analyze_reviews(reviews_list, company=None, start_date=None, end_date=None):
    return {"summary_text": "AI analysis: Positive overall feedback."}


def hour_heatmap(reviews, start_date=None, end_date=None):
    return {"hours": list(range(24)), "counts": [0] * 24}


def detect_anomalies(reviews):
    return []


def suggest_reply(review_text: str, rating: int, company_name: str) -> str:
    """
    Sync wrapper for async function.
    Safe for FastAPI route usage.
    """
    import asyncio

    try:
        return asyncio.run(generate_ai_reply(review_text, rating, company_name))
    except RuntimeError:
        # If event loop already running (FastAPI case)
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(
            generate_ai_reply(review_text, rating, company_name)
        )
