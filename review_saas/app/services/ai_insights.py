# FILE: app/services/ai_insights.py
import os
import google.generativeai as genai
from sqlalchemy.orm import Session
from ..models import Review, Company

genai.configure(api_key=os.getenv("GEMINI_API_KEY", "YOUR_KEY_HERE"))
model = genai.GenerativeModel('gemini-1.5-flash')

async def generate_ai_reply(review_text: str, rating: int, company_name: str) -> str:
    """Uses Gemini to draft a context-aware response."""
    prompt = f"Write a professional response for {company_name} to this {rating}-star review: '{review_text}'. Under 60 words."
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return "Thank you for your feedback. We value your input."

async def get_executive_summary(company_id: int, db: Session) -> str:
    """Generates a high-level summary of recent feedback trends."""
    reviews = db.query(Review).filter_by(company_id=company_id).limit(5).all()
    if not reviews: return "No data yet to summarize."
    
    text_blob = " ".join([r.text for r in reviews if r.text])
    prompt = f"Summarize these customer reviews in two sentences: {text_blob}"
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except:
        return "Reviews indicate a steady trend in customer satisfaction."
