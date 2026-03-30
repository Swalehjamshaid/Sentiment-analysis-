import os
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import google.generativeai as genai

# Core Imports
from app.core.db import get_session
from app.core.models import Review, Company

router = APIRouter(prefix="/chatbot", tags=["chatbot"])
logger = logging.getLogger(__name__)

# --- AI Configuration ---
# Uses the key from your Railway variables
raw_key = os.getenv("GEMINI_API_KEY", "AIzaSyB-J-JRHFepz-oKtre8zM3iXucAdM7BBn4")
API_KEY = raw_key.strip()

try:
    genai.configure(api_key=API_KEY)
    # Using gemini-pro for stability
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
        body = await request.json()
        company_id_raw = body.get("company_id")
        user_message = body.get("message", "").strip()

        if not company_id_raw:
            return JSONResponse({"answer": "AI Expert: No company selected on dashboard."})

        # --- STEP 1: AUTOMATIC NAME ALIGNMENT ---
        # We fetch the actual company object to get the 'name' as it appears on the dashboard
        company_id = int(company_id_raw)
        comp_stmt = select(Company).where(Company.id == company_id)
        comp_res = await session.execute(comp_stmt)
        company = comp_res.scalar_one_or_none()
        
        if not company:
            return JSONResponse({"answer": f"AI Expert: Company ID {company_id} not found in PostgreSQL."})

        # --- STEP 2: FETCH REVIEWS FROM POSTGRES ---
        rev_stmt = select(Review).where(Review.company_id == company_id).order_by(Review.date.desc()).limit(50)
        rev_res = await session.execute(rev_stmt)
        reviews = rev_res.scalars().all()
        
        # Logging for your Railway Terminal
        print(f"--- Chatbot Sync: {company.name} ---")
        print(f"Reviews found in DB: {len(reviews)}")

        if not reviews:
            return JSONResponse({"answer": f"AI Expert: I found **{company.name}**, but there are no reviews in the database. Please Sync Live Data first."})

        # --- STEP 3: CONTEXT & AI INSTRUCTION ---
        review_context = "\n".join([f"Rating: {r.rating} | Comment: {r.text}" for r in reviews])

        if model:
            # We explicitly tell the AI the name of the company from the DB
            prompt = f"""
            You are a Strategy Consultant for the business: {company.name}.
            
            Based ONLY on these {len(reviews)} reviews from the database:
            {review_context}
            
            User Question: {user_message}
            
            Instruction: Be professional. If there is a specific issue with {company.name}, identify it clearly.
            """
            
            response = model.generate_content(prompt)
            return JSONResponse({"answer": response.text})
        
        return JSONResponse({"answer": "AI Expert: Gemini API is not configured."})

    except Exception as e:
        logger.error(f"Chat Error: {e}")
        return JSONResponse({"answer": f"PostgreSQL Connection Error: {str(e)}"}, status_code=500)
