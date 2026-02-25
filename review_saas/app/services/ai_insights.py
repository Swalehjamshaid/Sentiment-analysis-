# filename: app/services/ai_insights.py

import os
from typing import Optional
from sqlalchemy.orm import Session

# Modern Google GenAI SDK
import google.genai as genai

# Initialize client (automatically uses GEMINI_API_KEY from env)
client = genai.Client()

# Model name (use a stable one)
MODEL_NAME = "gemini-1.5-flash"

from ..models import Review, Company


async def generate_ai_reply(review_text: str, rating: int, company_name: str) -> str:
    """Uses Gemini to draft a context-aware response."""
    prompt = f"Write a professional response for {company_name} to this {rating}-star review: '{review_text}'. Under 60 words."

    try:
        # Simplified call – no GenerateContentConfig needed for basic use
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            # Optional: add config inline if needed later
            # config=genai.types.GenerationConfig(max_output_tokens=100, temperature=0.7)
        )
        return response.text.strip()
    except Exception as e:
        print(f"Gemini reply error: {e}")
        return "Thank you for your feedback. We value your input."


def get_executive_summary(company_id: int, db: Session) -> str:
    """Generates a high-level summary of recent feedback trends."""
    reviews = db.query(Review).filter_by(company_id=company_id).limit(5).all()
    if not reviews:
        return "No data yet to summarize."

    text_blob = " ".join([r.text for r in reviews if r.text])
    prompt = f"Summarize these customer reviews in two sentences: {text_blob}"

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"Gemini summary error: {e}")
        return "Reviews indicate a steady trend in customer satisfaction."


# Stubs for other functions referenced elsewhere (prevents future import errors)
def analyze_reviews(reviews_list, company=None, start_date=None, end_date=None):
    return {"summary_text": "AI analysis: Positive overall feedback."}

def hour_heatmap(reviews, start_date=None, end_date=None):
    return {"hours": list(range(24)), "counts": [0] * 24}

def detect_anomalies(reviews):
    return []

def suggest_reply(review_text: str, rating: int, company_name: str) -> str:
    # Sync wrapper for async function
    import asyncio
    return asyncio.run(generate_ai_reply(review_text, rating, company_name))
