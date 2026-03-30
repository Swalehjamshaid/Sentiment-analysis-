import os
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import google.generativeai as genai

# Core Imports - Ensures connection to your PostgreSQL models
from app.core.db import get_session
from app.core.models import Review, Company

router = APIRouter(prefix="/chatbot", tags=["chatbot"])
logger = logging.getLogger(__name__)

# --- AI Configuration ---
# Securely pulls your key from Railway Environment Variables
raw_key = os.getenv("GEMINI_API_KEY", "AIzaSyB-J-JRHFepz-oKtre8zM3iXucAdM7BBn4")
API_KEY = raw_key.strip()

try:
    genai.configure(api_key=API_KEY)
    # Using gemini-pro for maximum stability with the Free Tier
    model = genai.GenerativeModel('gemini-pro')
except Exception as e:
    logger.error(f"Gemini Config Error: {e}")
    model = None

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
    try:
        # 1. Parse request from Dashboard.html
        body = await request.json()
        company_id = body.get("company_id")
        user_message = body.get("message", "").strip()

        if not company_id or not user_message:
            return JSONResponse({"answer": "AI Expert: Please select a business and enter a question."})

        # 2. THE DATABASE BRIDGE: Fetching reviews from PostgreSQL
        # This specifically pulls the records you see on your dashboard
        stmt = select(Review).where(Review.company_id == company_id).order_by(Review.date.desc()).limit(50)
        result = await session.execute(stmt)
        reviews = result.scalars().all()
        
        # Log for Railway terminal to verify DB connection
        print(f"DEBUG: Found {len(reviews)} reviews in Postgres for company {company_id}")

        if not reviews:
            return JSONResponse({"answer": "AI Expert: No review data found in the database for this business. Please click 'Sync Live Data' first."})

        # 3. CONTEXT INJECTION: Turning DB rows into a prompt for Gemini
        review_context = "\n".join([f"Rating: {r.rating} | Comment: {r.text}" for r in reviews])

        # 4. AI ANALYSIS
        if model:
            full_prompt = (
                f"You are a Business Intelligence Consultant. Use the following customer reviews "
                f"retrieved from our PostgreSQL database to answer the user's question.\n\n"
                f"DATASET:\n{review_context}\n\n"
                f"USER QUESTION: {user_message}\n\n"
                f"INSTRUCTIONS: Provide a professional, data-driven response based ONLY on the reviews above."
            )
            
            try:
                response = model.generate_content(full_prompt)
                if response and response.text:
                    return JSONResponse({"answer": response.text})
                else:
                    return JSONResponse({"answer": "AI Expert: I analyzed the data but could not generate a text response. Please try rephrasing."})
            except Exception as ai_err:
                logger.error(f"Gemini Execution Error: {ai_err}")
                return JSONResponse({"answer": "AI Expert: The AI service is currently throttled. Please wait 60 seconds."})
        
        return JSONResponse({"answer": "AI Expert: Gemini AI is not configured properly in Railway variables."})

    except Exception as e:
        logger.error(f"Chatbot Route Error: {e}")
        return JSONResponse({"answer": "AI Expert: System busy. Please refresh the dashboard."}, status_code=500)
