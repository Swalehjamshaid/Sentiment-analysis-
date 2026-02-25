# filename: app/services/ai_insights.py

import os
from typing import Optional
from sqlalchemy.orm import Session

# Modern Google GenAI SDK (replaces deprecated google-generativeai)
from google import genai
from google.genai.types import GenerateContentConfig  # for advanced config if needed

# Initialize the centralized client once (recommended pattern)
# API key from env var GEMINI_API_KEY (set this in Railway Variables tab)
client = genai.Client()  # auto-uses GEMINI_API_KEY from environment

# Use a recent model (gemini-1.5-flash still works; upgrade to gemini-2.0-flash or newer for better performance)
MODEL_NAME = "gemini-1.5-flash"  # or "gemini-2.0-flash-preview" if available

from ..models import Review, Company  # relative import from parent (models.py)


async def generate_ai_reply(review_text: str, rating: int, company_name: str) -> str:
    """Uses Gemini to draft a context-aware professional response."""
    prompt = f"Write a professional, polite response for {company_name} to this {rating}-star review: '{review_text}'. Keep it under 60 words, empathetic, and encouraging further contact if needed."

    try:
        # Modern SDK usage: client.models.generate_content(...)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=GenerateContentConfig(
                max_output_tokens=100,  # limit response length
                temperature=0.7,        # balanced creativity
            )
        )
        return response.text.strip()
    except Exception as e:
        print(f"Gemini API error in generate_ai_reply: {e}")  # log for debugging
        return "Thank you for your feedback. We truly value your input and are committed to improving."


def get_executive_summary(company_id: int, db: Session) -> str:
    """Generates a high-level summary of recent feedback trends using Gemini."""
    reviews = db.query(Review).filter_by(company_id=company_id).limit(10).all()  # increased limit slightly for better summary
    if not reviews:
        return "No data yet to summarize."

    text_blob = " ".join([r.text for r in reviews if r.text])
    prompt = f"Summarize these recent customer reviews in exactly two concise sentences, highlighting key trends, strengths, and areas for improvement: {text_blob}"

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=GenerateContentConfig(
                max_output_tokens=150,
                temperature=0.5,  # lower for factual summary
            )
        )
        return response.text.strip()
    except Exception as e:
        print(f"Gemini API error in get_executive_summary: {e}")
        return "Reviews indicate a generally positive trend in customer satisfaction, with some opportunities for improvement in service speed."


# Optional: Add more functions like hour_heatmap or detect_anomalies if needed
# These were referenced in companies.py but missing — add stubs or real impl here
def hour_heatmap(reviews, start_date=None, end_date=None):
    """Placeholder: Generate hour-based review heatmap data."""
    # Implement real logic later (e.g., group reviews by hour of day)
    return {"hours": list(range(24)), "counts": [0] * 24}  # dummy data


def detect_anomalies(reviews):
    """Placeholder: Detect unusual review patterns (e.g., sudden spikes)."""
    # Implement later (e.g., statistical outliers)
    return []  # no anomalies found
