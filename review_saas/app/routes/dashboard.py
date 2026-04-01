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
import io, base64
from wordcloud import WordCloud
from fpdf import FPDF
import asyncio

# OpenAI imports
import openai
import os

from app.core.db import get_session
from app.core.models import Company, Review, User

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Set OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")


# -----------------------------
# Fetch reviews with sentiment
# -----------------------------
async def fetch_reviews_with_sentiment(
    session: AsyncSession, company_id: int
) -> list[dict]:
    stmt = select(Review).where(Review.company_id == company_id)
    result = await session.execute(stmt)
    reviews = result.scalars().all()

    # If sentiment not already calculated, call OpenAI
    for review in reviews:
        if not review.sentiment_label:
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Analyze sentiment of the following text."},
                        {"role": "user", "content": review.text or ""}
                    ],
                    temperature=0
                )
                sentiment = response.choices[0].message.content.strip()
                review.sentiment_label = sentiment
                await session.commit()
            except Exception as e:
                review.sentiment_label = "unknown"
    return [
        {
            "id": r.id,
            "author": r.author_name,
            "text": r.text,
            "rating": r.rating,
            "sentiment_label": r.sentiment_label,
            "sentiment_score": r.sentiment_score,
            "date": r.google_review_time,
        }
        for r in reviews
    ]


# -----------------------------
# Word Cloud Generation
# -----------------------------
def generate_wordcloud(texts: list[str]) -> str:
    combined_text = " ".join(filter(None, texts))
    wc = WordCloud(width=800, height=400, background_color="white").generate(combined_text)
    buf = io.BytesIO()
    wc.to_image().save(buf, format="PNG")
    base64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    return base64_str


# -----------------------------
# Executive PDF Report
# -----------------------------
def create_pdf_report(company_name: str, reviews: list[dict]) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Executive Review Report - {company_name}", ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("Arial", "", 12)
    for r in reviews:
        pdf.multi_cell(0, 8, f"{r['author']} ({r['date']}): {r['text']}\nSentiment: {r['sentiment_label']}\nRating: {r['rating']}")
        pdf.ln(5)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


# -----------------------------
# Dashboard Overview Endpoint
# -----------------------------
@router.get("/overview/{company_id}", response_class=JSONResponse)
async def dashboard_overview(company_id: int, session: AsyncSession = Depends(get_session)):
    # Fetch company
    stmt = select(Company).where(Company.id == company_id)
    result = await session.execute(stmt)
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    reviews = await fetch_reviews_with_sentiment(session, company_id)

    avg_rating = sum(r["rating"] for r in reviews if r["rating"]) / (len(reviews) or 1)
    sentiment_counts = defaultdict(int)
    for r in reviews:
        sentiment_counts[r["sentiment_label"]] += 1

    wordcloud = generate_wordcloud([r["text"] for r in reviews])

    return {
        "company": {"id": company.id, "name": company.name},
        "average_rating": round(avg_rating, 2),
        "total_reviews": len(reviews),
        "sentiment_counts": sentiment_counts,
        "wordcloud_base64": wordcloud,
    }


# -----------------------------
# Chatbot Endpoint
# -----------------------------
@router.post("/chatbot/explain", response_class=JSONResponse)
async def chatbot_explain(question: str = Query(...)):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": question}],
            temperature=0.2
        )
        answer = response.choices[0].message.content.strip()
        return {"question": question, "answer": answer}
    except Exception as e:
        return {"error": str(e)}


# -----------------------------
# Executive PDF Endpoint
# -----------------------------
@router.get("/executive-report/pdf/{company_id}")
async def executive_pdf(company_id: int, session: AsyncSession = Depends(get_session)):
    stmt = select(Company).where(Company.id == company_id)
    result = await session.execute(stmt)
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    reviews = await fetch_reviews_with_sentiment(session, company_id)
    pdf_bytes = create_pdf_report(company.name, reviews)
    return FileResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", filename=f"{company.name}_report.pdf")
