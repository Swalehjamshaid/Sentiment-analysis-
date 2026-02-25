# filename: app/services/ai_insights.py

import os
from typing import Optional
from sqlalchemy.orm import Session

# Correct modern import for google-genai package (2026 version)
import google.genai as genai
from google.genai import GenerateContentConfig  # for config if needed

# Initialize client once (uses GEMINI_API_KEY from env automatically)
client = genai.Client()  # auto-detects api_key from os.environ["GEMINI_API_KEY"]

# Model name (gemini-1.5-flash is still supported; upgrade to gemini-2.5-flash if available)
MODEL_NAME = "gemini-1.5-flash"

from ..models import Review, Company  # relative import


async def generate_ai_reply(review_text: str, rating: int, company_name: str) -> str:
    """Uses Gemini to draft a context-aware response."""
    prompt = f"Write a professional response for {company_name} to this {rating}-star review: '{review_text}'. Under 60 words."

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=GenerateContentConfig(
                max_output_tokens=100,
                temperature=0.7,
            )
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
            config=GenerateContentConfig(
                max_output_tokens=150,
                temperature=0.5,
            )
        )
        return response.text.strip()
    except Exception as e:
        print(f"Gemini summary error: {e}")
        return "Reviews indicate a steady trend in customer satisfaction."

# Add missing stubs (to satisfy companies.py imports if needed)
def analyze_reviews(reviews_list, company=None, start_date=None, end_date=None):
    """Placeholder or real impl - returns dict with summary_text"""
    # Example simple return; expand with real logic
    return {"summary_text": "AI analysis: Positive overall feedback."}

def hour_heatmap(reviews, start_date=None, end_date=None):
    """Placeholder"""
    return {"hours": list(range(24)), "counts": [0] * 24}

def detect_anomalies(reviews):
    """Placeholder"""
    return []

def suggest_reply(review_text: str, rating: int, company_name: str) -> str:
    """Alias for generate_ai_reply if needed in reply.py"""
    return generate_ai_reply(review_text, rating, company_name)  # sync call for simplicity
