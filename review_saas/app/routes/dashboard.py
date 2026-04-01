# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD (PRODUCTION READY)
# ==========================================================

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from collections import defaultdict
import io
import base64
import os
import logging
import asyncio

# External Libraries
from wordcloud import WordCloud
from fpdf import FPDF
import openai

# Internal Core Imports
from app.core.db import get_session
from app.core.models import Company, Review, User

# --------------------------- Setup ---------------------------
logger = logging.getLogger("app.routes.dashboard")

# The prefix here is "/dashboard". 
# Combined with main.py's "/api", the full path is "/api/dashboard"
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Set OpenAI API key from environment
openai.api_key = os.getenv("OPENAI_API_KEY")

# ----------------------------------------------------------
# HELPER: Fetch & Analyze Sentiment
# ----------------------------------------------------------
async def fetch_reviews_with_sentiment(
    session: AsyncSession, company_id: int
) -> list[dict]:
    """
    Fetches reviews for a company. If sentiment is missing, 
    it uses OpenAI to generate it on-the-fly.
    """
    stmt = select(Review).where(Review.company_id == company_id)
    result = await session.execute(stmt)
    reviews = result.scalars().all()

    if not reviews:
        return []

    for review in reviews:
        # If sentiment_label is empty or null, run AI analysis
        if not review.sentiment_label or review.sentiment_label.lower() == "unknown":
            try:
                # Using gpt-4o-mini for cost-effective sentiment analysis
                response = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a sentiment analyzer. Respond with only one word: Positive, Negative, or Neutral."},
                        {"role": "user", "content": f"Analyze this review: {review.text or ''}"}
                    ],
                    temperature=0
                )
                sentiment = response.choices[0].message.content.strip().capitalize()
                review.sentiment_label = sentiment
                # Commit individual updates to ensure data persists even if loop breaks
                await session.commit()
            except Exception as e:
                logger.error(f"Error analyzing sentiment for review {review.id}: {e}")
                review.sentiment_label = "Neutral"

    return [
        {
            "id": r.id,
            "author": r.author_name,
            "text": r.text,
            "rating": r.rating or 0,
            "sentiment_label": r.sentiment_label or "Neutral",
            "sentiment_score": r.sentiment_score or 0,
            "date": str(r.google_review_time) if r.google_review_time else "Unknown",
        }
        for r in reviews
    ]

# ----------------------------------------------------------
# HELPER: Visuals & Reports
# ----------------------------------------------------------
def generate_wordcloud(texts: list[str]) -> str:
    combined_text = " ".join(filter(None, texts))
    if not combined_text.strip():
        return ""
    
    wc = WordCloud(width=800, height=400, background_color="white").generate(combined_text)
    buf = io.BytesIO()
    wc.to_image().save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def create_pdf_report(company_name: str, reviews: list[dict]) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Executive Review Report: {company_name}", ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("Arial", "", 10)
    for r in reviews:
        text_snippet = (r['text'][:150] + '...') if len(r['text']) > 150 else r['text']
        line = f"[{r['rating']}*] {r['author']} - {r['sentiment_label']}\n{text_snippet}\n"
        pdf.multi_cell(0, 6, line)
        pdf.ln(2)

    return pdf.output(dest='S').encode('latin-1')

# ----------------------------------------------------------
# ENDPOINT: Dashboard Overview
# ----------------------------------------------------------
@router.get("/overview/{company_id}", response_class=JSONResponse)
async def dashboard_overview(company_id: int, session: AsyncSession = Depends(get_session)):
    """
    Main endpoint for the dashboard UI.
    """
    # 1. Verify Company exists
    stmt = select(Company).where(Company.id == company_id)
    result = await session.execute(stmt)
    company = result.scalars().first()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # 2. Get reviews (with AI sentiment check)
    reviews = await fetch_reviews_with_sentiment(session, company_id)

    if not reviews:
        return {
            "company": {"id": company.id, "name": company.name},
            "average_rating": 0,
            "total_reviews": 0,
            "sentiment_counts": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "wordcloud_base64": "",
            "message": "No reviews found for this business. Please sync data first."
        }

    # 3. Calculate Stats
    total_reviews = len(reviews)
    avg_rating = sum(r["rating"] for r in reviews) / total_reviews
    
    sentiment_counts = defaultdict(int)
    for r in reviews:
        label = r["sentiment_label"]
        sentiment_counts[label] += 1

    # 4. Generate WordCloud
    wordcloud = generate_wordcloud([r["text"] for r in reviews])

    return {
        "company": {"id": company.id, "name": company.name},
        "average_rating": round(avg_rating, 2),
        "total_reviews": total_reviews,
        "sentiment_counts": dict(sentiment_counts),
        "wordcloud_base64": wordcloud,
    }

# ----------------------------------------------------------
# ENDPOINT: AI Insights Chat
# ----------------------------------------------------------
@router.post("/chatbot/explain", response_class=JSONResponse)
async def chatbot_explain(question: str = Query(...)):
    """
    AI Chatbot to explain dashboard trends.
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a business consultant for Review Intel AI. Provide concise, actionable insights."},
                {"role": "user", "content": question}
            ],
            temperature=0.2
        )
        answer = response.choices[0].message.content.strip()
        return {"question": question, "answer": answer}
    except Exception as e:
        logger.error(f"Chatbot Error: {e}")
        return {"error": "Failed to connect to AI engine."}

# ----------------------------------------------------------
# ENDPOINT: Executive PDF Export
# ----------------------------------------------------------
@router.get("/executive-report/pdf/{company_id}")
async def executive_pdf(company_id: int, session: AsyncSession = Depends(get_session)):
    """
    Generates a downloadable PDF report.
    """
    stmt = select(Company).where(Company.id == company_id)
    result = await session.execute(stmt)
    company = result.scalars().first()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    reviews = await fetch_reviews_with_sentiment(session, company_id)
    
    if not reviews:
        raise HTTPException(status_code=400, detail="No reviews available to generate report.")

    pdf_content = create_pdf_report(company.name, reviews)
    
    return FileResponse(
        io.BytesIO(pdf_content), 
        media_type="application/pdf", 
        filename=f"Report_{company.name.replace(' ', '_')}.pdf"
    )
