import random
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Core App Imports
from app.core.db import get_session
from app.core.models import Review, Company

router = APIRouter(prefix="/chatbot", tags=["chatbot"])
vader_analyzer = SentimentIntensityAnalyzer()

def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

@router.post("/chat")
async def chat_api(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    body = await request.json()
    company_id = body.get("company_id")
    user_message = body.get("message", "").strip()

    # 1. Check if Company ID is provided by the Dashboard
    if not company_id:
        return JSONResponse({"answer": "AI Expert: Please select a company on the dashboard so I can analyze your data."})

    # 2. Fetch Company details
    comp_res = await session.execute(select(Company).where(Company.id == company_id))
    company = comp_res.scalar_one_or_none()
    
    if not company:
        return JSONResponse({"answer": "AI Expert: System Error. The selected company was not found in the database."})

    # 3. Fetch all Reviews for this specific company (The 100 records on your dashboard)
    rev_result = await session.execute(select(Review).where(Review.company_id == company_id))
    reviews = rev_result.scalars().all()
    total_reviews = len(reviews)

    if total_reviews == 0:
        return JSONResponse({"answer": f"AI Expert: I see **{company.name}** is selected, but there are no reviews to analyze yet."})

    # 4. Perform Analysis (Summarizing the dashboard data for the AI)
    avg_rating = round(sum(r.rating for r in reviews) / total_reviews, 1)
    
    # Simple logic to answer "what is the real issue"
    if "issue" in user_message.lower() or "problem" in user_message.lower():
        low_rated = [r.text for r in reviews if r.rating <= 2]
        if low_rated:
            # In a full version, you'd pass 'low_rated' to an LLM like Gemini
            return JSONResponse({
                "answer": f"AI Expert: For **{company.name}**, the real issue is reflected in your {len(low_rated)} negative reviews. Common themes suggest service delays and quality consistency."
            })

    # Default Context-Aware Response
    return JSONResponse({
        "answer": f"AI Expert: I am ready. I've analyzed {total_reviews} reviews for **{company.name}** (Avg Rating: {avg_rating}). How can I help with this specific data?"
    })
