import os
import random
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import google.generativeai as genai

# Core App Imports
from app.core.db import get_session
from app.core.models import Review, Company

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

# --- AI Configuration ---
# Pulls the key from your Railway Environment Variables
API_KEY = os.getenv("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)
    # Using flash for high speed and low latency on your dashboard
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
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
        # 1. Parse JSON Body from Dashboard.html
        body = await request.json()
        company_id = body.get("company_id")
        user_message = body.get("message", "").strip()

        # Validation
        if not user_message:
            return JSONResponse({"answer": "AI Expert: Please type a message to begin."})
        
        if not company_id:
            return JSONResponse({"answer": "AI Expert: Please select a business on the dashboard first."})

        # 2. Fetch Company Name from Database
        comp_res = await session.execute(select(Company).where(Company.id == company_id))
        company = comp_res.scalar_one_or_none()
        
        if not company:
            return JSONResponse({"answer": "AI Expert: The selected business could not be found."})

        # 3. Fetch Reviews for Context (Pulling up to 100 records for analysis)
        rev_res = await session.execute(
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.date.desc())
            .limit(100)
        )
        reviews = rev_res.scalars().all()
        
        if not reviews:
            return JSONResponse({"answer": f"AI Expert: I've connected to **{company.name}**, but no review data has been synced yet."})

        # 4. Format Reviews for the AI to "read"
        review_context = ""
        for i, r in enumerate(reviews, 1):
            review_context += f"{i}. Rating: {r.rating}/5 | Comment: {r.text}\n"

        # 5. Execute Gemini AI Logic
        if model:
            system_instruction = f"""
            You are a Strategy Consultant for {company.name}. 
            You are looking at a dashboard with {len(reviews)} customer reviews.
            
            CONTEXT DATA (Latest Reviews):
            {review_context}
            
            YOUR GOAL:
            Answer the user's question accurately based ONLY on the reviews provided. 
            If they ask "what is the real issue," summarize the most frequent negative complaints.
            Keep your answer professional, concise, and focused on business improvement.
            """
            
            # Send message to Gemini
            response = model.generate_content([system_instruction, f"User Query: {user_message}"])
            ai_answer = response.text
        else:
            # Fallback if the Library or API Key is missing
            ai_answer = "AI Expert: I'm currently in 'Offline Mode'. Please ensure the GEMINI_API_KEY is set in Railway."

        return JSONResponse({"answer": ai_answer})

    except Exception as e:
        # Log the error for Railway logs and return a safe message
        print(f"DEBUG CHATBOT ERROR: {str(e)}")
        return JSONResponse(
            {"answer": "AI Expert: I encountered a technical issue while analyzing the records. Please try again."},
            status_code=500
        )
