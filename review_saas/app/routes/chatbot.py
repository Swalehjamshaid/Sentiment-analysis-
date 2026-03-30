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

# Set up logging so you can see errors in Railway terminal
logger = logging.getLogger(__name__)

# --- AI Configuration ---
API_KEY = os.getenv("GEMINI_API_KEY")

if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        logger.error(f"Failed to configure Gemini: {e}")
        model = None
else:
    logger.warning("GEMINI_API_KEY not found in environment variables")
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

        if not user_message or not company_id:
            return JSONResponse({"answer": "AI Expert: Please select a company and type your question."})

        # 1. Fetch Company & Reviews
        comp_res = await session.execute(select(Company).where(Company.id == company_id))
        company = comp_res.scalar_one_or_none()
        
        if not company:
            return JSONResponse({"answer": "AI Expert: Business not found."})

        rev_res = await session.execute(
            select(Review).where(Review.company_id == company_id).limit(50)
        )
        reviews = rev_res.scalars().all()
        
        # 2. Build AI Context
        review_context = "\n".join([f"Rating: {r.rating} | {r.text}" for r in reviews])
        
        # 3. Call AI
        if model:
            full_prompt = (
                f"You are a consultant for {company.name}. Based on these reviews:\n"
                f"{review_context}\n\n"
                f"User asks: {user_message}"
            )
            # Use a timeout or try/except specifically for the AI generation
            try:
                response = model.generate_content(full_prompt)
                ai_answer = response.text
            except Exception as ai_err:
                logger.error(f"Gemini Generation Error: {ai_err}")
                ai_answer = "AI Expert: I could not generate a response. Please check your API quota or key status."
        else:
            ai_answer = "AI Expert: Gemini API is not configured. Please check Railway environment variables."

        return JSONResponse({"answer": ai_answer})

    except Exception as e:
        logger.error(f"General Chatbot Error: {e}")
        return JSONResponse({"answer": f"AI Expert: System Error ({str(e)})"}, status_code=500)
