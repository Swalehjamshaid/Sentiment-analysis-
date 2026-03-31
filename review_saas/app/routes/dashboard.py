# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD (RAILWAY READY ✅)
# ==========================================================

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from typing import Optional
from collections import defaultdict
import os

from app.db import get_async_session
from app.models import Review, Company  # Assuming models exist
from app.ai import generate_insights, ask_ai_question  # Assuming AI functions exist
from app.utils import generate_pdf_report  # Utility for PDF reports

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# -------------------------
# KPI & Visualization Endpoint
# -------------------------
@router.get("/ai/insights")
async def get_insights(
    company_id: int = Query(..., description="Company ID"),
    start: Optional[str] = Query("2010-01-01"),
    end: Optional[str] = Query(datetime.today().strftime("%Y-%m-%d")),
    session: AsyncSession = Depends(get_async_session)
):
    try:
        # Fetch reviews for the company in the date range
        stmt = select(Review).where(
            Review.company_id == company_id,
            Review.created_at >= start,
            Review.created_at <= end
        )
        result = await session.execute(stmt)
        reviews = result.scalars().all()

        total_reviews = len(reviews)
        average_rating = round(sum(r.rating for r in reviews)/total_reviews, 2) if reviews else 0

        # Sentiment + Emotion Analysis via AI
        visualizations = generate_insights(reviews)

        return JSONResponse({
            "metadata": {"total_reviews": total_reviews},
            "kpis": {
                "average_rating": average_rating,
                "reputation_score": visualizations.get("reputation_score", "—"),
            },
            "visualizations": visualizations
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------
# Revenue Risk Endpoint
# -------------------------
@router.get("/revenue")
async def get_revenue_risk(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session)
):
    # Dummy risk calculation, replace with your logic
    risk_percent = 25  # Placeholder
    impact = "Medium"
    return JSONResponse({
        "risk_percent": risk_percent,
        "impact": impact
    })

# -------------------------
# AI Chat Endpoint
# -------------------------
@router.get("/chatbot/explain/{company_id}")
async def chat_ai(
    company_id: int,
    question: str = Query(..., description="Question for AI"),
    session: AsyncSession = Depends(get_async_session)
):
    try:
        answer = await ask_ai_question(company_id, question)
        return JSONResponse({"answer": answer})
    except Exception as e:
        return JSONResponse({"answer": f"AI error: {str(e)}"})

# -------------------------
# Executive PDF Report
# -------------------------
@router.get("/executive-report/pdf/{company_id}")
async def download_report(
    company_id: int,
    session: AsyncSession = Depends(get_async_session)
):
    try:
        pdf_path = await generate_pdf_report(company_id)
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="Report not found")
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"report_{company_id}.pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------
# Load Companies
# -------------------------
@router.get("/companies", tags=["companies"])
async def list_companies(session: AsyncSession = Depends(get_async_session)):
    stmt = select(Company)
    result = await session.execute(stmt)
    companies = result.scalars().all()
    data = [{"id": c.id, "name": c.name} for c in companies]
    return JSONResponse({"companies": data})

# -------------------------
# Sync / Ingest Reviews
# -------------------------
@router.post("/reviews/ingest/{company_id}")
async def ingest_reviews(company_id: int):
    # Placeholder: Replace with your actual ingestion logic
    # e.g., call Google Reviews scraper for the company
    return JSONResponse({"status": "success", "message": f"Reviews ingested for company {company_id}"})
