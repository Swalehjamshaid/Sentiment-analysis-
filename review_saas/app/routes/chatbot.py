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

# --- HARDCODED AI CONFIGURATION ---
# Placing the key directly here as requested to ensure 100% connectivity
API_KEY = "AIzaSyB-J-JRHFepz-oKtre8zM3iXucAdM7BBn4"

try:
    genai.configure(api_key=API_KEY)
    # Using 'gemini-pro' for maximum stability in your region
    model = genai.GenerativeModel('gemini-pro')
except Exception as e:
    logger.error(f"Gemini Config Error: {e}")
    model = None

@router.post("/chat")
async def chat_api(
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    try:
        # 1. Check Session/User
        user = request.session.get("user")
        if not user:
            # If session is lost, we still try to respond but warn the user
            logger.warning("Chatbot accessed without active session")

        # 2. Parse Dashboard Data
        body = await request.json()
        company_id_raw = body.get("company_id")
        user_message = body.get("message", "").strip()

        if not company_id_raw or company_id_raw == "null":
            return JSONResponse({"answer": "AI Expert: Please select a business from the dashboard dropdown first."})

        # 3. Database Sync: Align with Company Name
        try:
            company_id = int(company_id_raw)
        except (ValueError, TypeError):
            return JSONResponse({"answer": "AI Expert: Invalid Business ID. Please re-select the business."})

        comp_stmt = select(Company).where(Company.id == company_id)
        comp_res = await session.execute(comp_stmt)
        company = comp_res.scalar_one_or_none()
        
        if not company:
            return JSONResponse({"answer": f"AI Expert: I cannot find Business ID {company_id} in the PostgreSQL database."})

        # 4. Fetch Reviews for Analysis
        rev_stmt = select(Review).where(Review.company_id == company_id).order_by(Review.date.desc()).limit(40)
        rev_res = await session.execute(rev_stmt)
        reviews = rev_res.scalars().all()
        
        # Logging for Railway Deploy Logs
        print(f"--- Chatbot Analysis for: {company.name} ---")
        print(f"Reviews found: {len(reviews)}")

        # 5. Generate AI Response
        if model:
            # Create the context from Postgres data
            if reviews:
                review_context = "\n".join([f"Rating: {r.rating}* | {r.text}" for r in reviews])
                prompt = f"""
                You are a Business Consultant for {company.name}.
                Analyze these customer reviews from our database:
                {review_context}
                
                User Question: {user_message}
                
                Instruction: Provide a professional, concise answer based on the review data.
                """
            else:
                # Fallback if no reviews exist yet
                prompt = f"The user is asking about {company.name}, but there are no reviews in the database. Tell them to click 'Sync Live Data'. User asked: {user_message}"

            response = model.generate_content(prompt)
            
            if response and response.text:
                return JSONResponse({"answer": response.text})
            else:
                return JSONResponse({"answer": "AI Expert: I processed the data but the AI did not return text. Please try a different question."})
        
        return JSONResponse({"answer": "AI Expert: Gemini AI Model is not initialized."})

    except Exception as e:
        logger.error(f"Chatbot Critical Error: {e}")
        return JSONResponse({"answer": f"AI Expert Error: {str(e)}"}, status_code=500)
