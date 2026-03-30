import os
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import google.generativeai as genai

# Core App Imports
from app.core.db import get_session
from app.core.models import Review, Company

router = APIRouter(prefix="/chatbot", tags=["chatbot"])
logger = logging.getLogger(__name__)

# --- AI Configuration ---
# 1. Pulls the key from Railway. 
# 2. Uses .strip() to fix any accidental spaces in the Railway UI.
raw_key = os.getenv("GEMINI_API_KEY", "AIzaSyB-J-JRHFepz-oKtre8zM3iXucAdM7BBn4")
API_KEY = raw_key.strip()

try:
    genai.configure(api_key=API_KEY)
    # Changed to gemini-pro for better stability on Free Tier keys
    model = genai.GenerativeModel('gemini-pro')
    logger.info("Chatbot: Gemini configured successfully.")
except Exception as e:
    logger.error(f"Chatbot: Configuration Error: {e}")
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
        company_id = body.get("company_id")
        user_message = body.get("message", "").strip()

        # Validation: Check for message and company selection
        if not user_message:
            return JSONResponse({"answer": "AI Expert: Please type a question."})
        
        if not company_id:
            return JSONResponse({"answer": "AI Expert: Please select a business on the dashboard first."})

        # 1. Fetch Company & Reviews
        comp_res = await session.execute(select(Company).where(Company.id == company_id))
        company = comp_res.scalar_one_or_none()
        
        if not company:
            return JSONResponse({"answer": "AI Expert: Selected business not found."})

        # Limit to 30 reviews to stay within Gemini Free Tier safety limits
        rev_res = await session.execute(
            select(Review).where(Review.company_id == company_id).limit(30)
        )
        reviews = rev_res.scalars().all()
        
        if not reviews:
            return JSONResponse({"answer": f"AI Expert: I've connected to **{company.name}**, but no review data has been synced yet."})

        # 2. Prepare context for AI
        review_context = "\n".join([f"Rating: {r.rating} | Text: {r.text}" for r in reviews])

        # 3. Generate AI Response
        if model:
            try:
                system_prompt = (
                    f"You are a Business Consultant for {company.name}.\n"
                    f"Analyze these latest reviews:\n{review_context}\n\n"
                    f"User Question: {user_message}\n"
                    f"Provide a helpful, professional, and concise answer."
                )
                
                response = model.generate_content(system_prompt)
                
                if response and response.text:
                    return JSONResponse({"answer": response.text})
                else:
                    return JSONResponse({"answer": "AI Expert: I analyzed the data but couldn't form a response. Try asking specifically about the complaints."})
            
            except Exception as ai_err:
                logger.error(f"Gemini AI Error: {ai_err}")
                return JSONResponse({"answer": "AI Expert: The AI service is currently busy or hit a quota limit. Please try again in 1 minute."})
        
        return JSONResponse({"answer": "AI Expert: Gemini is not configured. Check your API Key in Railway Variables."})

    except Exception as e:
        logger.error(f"General Chatbot Error: {e}")
        return JSONResponse({"answer": "AI Expert: System Error. Please refresh and try again."}, status_code=500)
